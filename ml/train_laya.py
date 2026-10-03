"""Fine tunes Laya (typed-decisions checkpoint) on MediThread's own labelled data (ml/data/train.jsonl).

Adapted from the Apple Silicon script in github.com/NandhaKishorM/laya (Apache-2.0): same RLCD loss, same
calibration, but it reads our local JSONL instead of a Hub dataset, runs on CUDA (Colab), and can freeze the lower
encoder layers so it fits in 8 GB of Apple Silicon memory.

    # Colab / any CUDA GPU (full fine-tune, about 20-40 minutes for ~4k rows)
    python ml/train_laya.py --device cuda --epochs 3 --micro-batch 8 --grad-accum 4

    # 8 GB Mac (MPS), lower 20 of 28 encoder layers frozen
    python ml/train_laya.py --device mps --freeze-below 20 --epochs 2 --micro-batch 2 --grad-accum 16

Output: ml/out/laya-medithread/ (model.safetensors, encoder/, tokenizer/, rl_agent_config.json with fitted
temperatures). Copy that folder to models/laya/ for the service, then run ml/eval.py.
"""
from __future__ import annotations

import argparse
import gc
import json
import math
import random
import re
import time
from pathlib import Path

import torch
from huggingface_hub import snapshot_download
from safetensors.torch import load_file, save_file
from transformers import AutoTokenizer

from laya.agent import _fix_tokenizer_config
from laya.common import QTYPES, build_model, build_sequence, proper_reward, render_options

ROOT = Path(__file__).resolve().parent
MODEL_ID = "convaiinnovations/laya"
BASE_SUBFOLDER = "typed-decisions"


def choose_device(requested: str) -> torch.device:
    if requested == "auto":
        if torch.cuda.is_available():
            return torch.device("cuda")
        return torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    return torch.device(requested)


def prepare_base(base_dir: Path) -> Path:
    model_dir = base_dir / BASE_SUBFOLDER
    if not (model_dir / "model.safetensors").exists():
        print(f"downloading {MODEL_ID}/{BASE_SUBFOLDER} ...")
        snapshot_download(MODEL_ID, allow_patterns=[f"{BASE_SUBFOLDER}/*"], local_dir=str(base_dir))
    _fix_tokenizer_config(str(model_dir))
    return model_dir


def build_item(tokenizer, cfg, state, question, gold_q):
    qtype, criteria = question["type"], question.get("criteria", {})
    if qtype == "choice":
        target = [gold_q["probabilities"].get(k, 0.0) for k in criteria.keys()]
    elif qtype == "noul":
        target = [gold_q["probabilities"].get("false", 0.5), gold_q["probabilities"].get("true", 0.5)]
    else:
        return None
    total = sum(target)
    target = [t / total for t in target] if total > 0 else [1.0 / len(target)] * len(target)
    n_options = len(render_options({"t": qtype, "crit": criteria}))
    seq, markers = build_sequence(tokenizer, state, {"t": qtype, "ins": question["instructions"], "crit": criteria},
                                  cfg["max_len"], cfg["head_max_len"])
    if len(markers) != n_options:
        return None
    return {"ids": seq, "markers": markers, "qtype": QTYPES[qtype], "target": target, "label": target.index(max(target))}


def load_items(path: Path, tokenizer, cfg) -> list[dict]:
    items, skipped = [], 0
    for line in path.open(encoding="utf-8"):
        row = json.loads(line)
        state, questions, gold = json.loads(row["state"]), json.loads(row["questions"]), json.loads(row["gold"])
        for qid, q in questions.items():
            if qid in gold:
                it = build_item(tokenizer, cfg, state, q, gold[qid])
                if it is None:
                    skipped += 1
                else:
                    items.append(it)
    print(f"{len(items)} training items from {path.name} (skipped {skipped})")
    return items


def collate(items, pad_id):
    b, n = len(items), max(len(i["ids"]) for i in items)
    k = max(len(i["markers"]) for i in items)
    ids = torch.full((b, n), pad_id, dtype=torch.long)
    att = torch.zeros((b, n), dtype=torch.long)
    pos = torch.zeros((b, k), dtype=torch.long)
    mask = torch.zeros((b, k), dtype=torch.bool)
    tgt = torch.zeros((b, k), dtype=torch.float32)
    for r, it in enumerate(items):
        L = len(it["ids"])
        ids[r, :L] = torch.tensor(it["ids"])
        att[r, :L] = 1
        m = len(it["markers"])
        pos[r, :m] = torch.tensor(it["markers"])
        mask[r, :m] = True
        tgt[r, : len(it["target"])] = torch.tensor(it["target"])
    return ids, att, pos, mask, tgt, torch.tensor([i["qtype"] for i in items], dtype=torch.long)


def fit_temperature(samples):
    if len(samples) < 10:
        return 1.0
    kmax = max(len(l) for l, _ in samples)
    logits = torch.full((len(samples), kmax), -1e4)
    targets = torch.zeros((len(samples), kmax))
    for i, (v, t) in enumerate(samples):
        logits[i, : len(v)] = torch.as_tensor(v)
        targets[i, : len(t)] = torch.as_tensor(t, dtype=torch.float32)
    log_t = torch.zeros(1, requires_grad=True)
    opt = torch.optim.LBFGS([log_t], lr=0.1, max_iter=100)

    def closure():
        opt.zero_grad()
        loss = -(targets * torch.log_softmax(logits / log_t.exp(), -1)).sum(-1).mean()
        loss.backward()
        return loss

    opt.step(closure)
    return float(torch.clamp(log_t.exp(), 0.1, 10.0).item())


def save(model, tokenizer, cfg, out: Path):
    out.mkdir(parents=True, exist_ok=True)
    save_file({n: v.detach().half().cpu().contiguous() for n, v in model.state_dict().items()}, str(out / "model.safetensors"))
    model.encoder.config.save_pretrained(out / "encoder")
    tokenizer.save_pretrained(out / "tokenizer")
    (out / "rl_agent_config.json").write_text(json.dumps(cfg, indent=2))


def freeze_lower(model, below: int) -> None:
    """Freezes embeddings and encoder layers 0..below-1 (saves optimizer memory on small machines)."""
    n_frozen = 0
    for name, p in model.named_parameters():
        m = re.search(r"encoder\.layers\.(\d+)\.", name)
        if "embeddings" in name or (m and int(m.group(1)) < below):
            p.requires_grad_(False)
            n_frozen += p.numel()
    print(f"frozen {n_frozen / 1e6:.0f}M of {sum(p.numel() for p in model.parameters()) / 1e6:.0f}M parameters")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", default=str(ROOT / "data" / "train.jsonl"))
    ap.add_argument("--base-dir", default=str(ROOT / "base"))
    ap.add_argument("--out", default=str(ROOT / "out" / "laya-medithread"))
    ap.add_argument("--device", default="auto", choices=["auto", "cuda", "mps", "cpu"])
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--micro-batch", type=int, default=4)
    ap.add_argument("--grad-accum", type=int, default=8)
    ap.add_argument("--freeze-below", type=int, default=0, help="freeze embeddings + this many lower encoder layers")
    ap.add_argument("--calib-max", type=int, default=400)
    ap.add_argument("--max-items", type=int, default=0, help="debug: use only this many items")
    ap.add_argument("--no-checkpointing", action="store_true")
    args = ap.parse_args()

    torch.set_float32_matmul_precision("high")
    device = choose_device(args.device)
    model_dir = prepare_base(Path(args.base_dir))
    cfg = json.loads((model_dir / "rl_agent_config.json").read_text())
    cfg.update({"max_tokens_per_batch": 2048, "max_len": 1024, "head_max_len": 256})
    if not args.no_checkpointing:
        cfg["gradient_checkpointing"] = True

    tokenizer = AutoTokenizer.from_pretrained(model_dir / "tokenizer")
    model = build_model(cfg, encoder_dir=model_dir / "encoder")
    model.load_state_dict(load_file(str(model_dir / "model.safetensors")), strict=True)
    model.float()
    if not args.no_checkpointing:
        model.encoder.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
        model.head_checkpointing = True
    if args.freeze_below:
        freeze_lower(model, args.freeze_below)
    model.to(device).train()

    items = load_items(Path(args.train), tokenizer, cfg)
    random.Random(20261002).shuffle(items)
    if args.max_items:
        items = items[: args.max_items]
    n_cal = min(args.calib_max, len(items) // 10)
    calib, train = items[:n_cal], items[n_cal:]

    enc = [p for n, p in model.named_parameters() if "encoder." in n and p.requires_grad]
    head = [p for n, p in model.named_parameters() if "encoder." not in n and p.requires_grad]
    opt = torch.optim.AdamW([{"params": enc, "lr": 2.5e-5}, {"params": head, "lr": 1e-4}], weight_decay=0.01)
    updates = max(1, math.ceil(len(train) / args.micro_batch / args.grad_accum) * args.epochs)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=updates, eta_min=1e-6)
    print(f"device={device} train={len(train)} calib={len(calib)} updates={updates}")

    t0 = time.time()
    for epoch in range(args.epochs):
        random.Random(42 + epoch).shuffle(train)
        opt.zero_grad(set_to_none=True)
        total, nb = 0.0, 0
        sigma = 0.4 + (0.1 - 0.4) * epoch / max(1, args.epochs - 1)
        for start in range(0, len(train), args.micro_batch):
            ids, att, pos, mask, tgt, qt = (x.to(device) for x in collate(train[start:start + args.micro_batch], tokenizer.pad_token_id))
            logits, act = model(ids, att, pos, mask, qt)
            logits = logits.float()
            k = mask.sum(-1, keepdim=True).float()
            eps = torch.randn((4,) + logits.shape, device=device) * sigma * mask
            eps = (eps - eps.sum(-1, keepdim=True) / k) * mask
            noisy = logits.detach().unsqueeze(0) + eps
            probs = torch.softmax(noisy.masked_fill(~mask, -1e4), -1)
            with torch.no_grad():
                reward = proper_reward(probs, tgt.unsqueeze(0), qt, mask, w_sph=0.75, w_rps=1.0)
                adv = reward - reward.mean(0, keepdim=True)
                adv = adv / (adv.std() + 1e-6)
            logp = -(((noisy - logits.unsqueeze(0)) ** 2) * mask).sum(-1) / (2 * sigma ** 2)
            loss = (-(adv * logp).mean() - (tgt * torch.log_softmax(logits.masked_fill(~mask, -1e4), -1)).sum(-1).mean()
                    + 0.0 * act.sum()) / args.grad_accum
            loss.backward()
            nb += 1
            if nb % args.grad_accum == 0 or start + args.micro_batch >= len(train):
                torch.nn.utils.clip_grad_norm_([p for p in model.parameters() if p.requires_grad], 1.0)
                opt.step()
                sched.step()
                opt.zero_grad(set_to_none=True)
            total += loss.item() * args.grad_accum
            if nb % 50 == 0:
                print(f"epoch {epoch + 1}/{args.epochs} step {nb}/{math.ceil(len(train) / args.micro_batch)} "
                      f"loss={loss.item() * args.grad_accum:.4f} elapsed={(time.time() - t0) / 60:.1f}m", flush=True)
        print(f"epoch {epoch + 1} done, avg loss {total / max(1, nb):.4f}", flush=True)

    print("calibrating temperatures ...")
    model.eval()
    groups = [[] for _ in range(3)]
    with torch.no_grad():
        for start in range(0, len(calib), args.micro_batch):
            chunk = calib[start:start + args.micro_batch]
            ids, att, pos, mask, tgt, qt = (x.to(device) for x in collate(chunk, tokenizer.pad_token_id))
            logits, _ = model(ids, att, pos, mask, qt)
            for i, it in enumerate(chunk):
                groups[it["qtype"]].append((logits[i, : len(it["markers"])].float().cpu(), it["target"]))
    temps = [fit_temperature(g) if g else 1.2 for g in groups]
    cfg.update({"fine_tuned": True, "model_name": "laya-medithread", "temperature": temps,
                "training": {"rows": len(train), "epochs": args.epochs, "freeze_below": args.freeze_below,
                             "base": f"{MODEL_ID}/{BASE_SUBFOLDER}", "minutes": round((time.time() - t0) / 60, 1)}})
    cfg.pop("temperature_by_options", None)
    save(model, tokenizer, cfg, Path(args.out))
    print(f"saved to {args.out}; temperatures {temps}")
    del model
    gc.collect()


if __name__ == "__main__":
    main()
