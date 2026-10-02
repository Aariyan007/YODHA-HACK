import { useEffect, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { agentShareQr } from "../../api/client.js";
import { appUrl } from "../../routing.js";

// The real share link the agent just made (confirmed by the person). The token is fetched here, once, with their login.
export default function AgentQR({ qr }) {
  const [share, setShare] = useState(null);
  const [err, setErr] = useState(false);
  useEffect(() => {
    let live = true;
    agentShareQr(qr.ref).then((s) => live && setShare(s)).catch(() => live && setErr(true));
    return () => { live = false; };
  }, [qr.ref]);
  if (err) return <p className="ag-res-note">This code is no longer available to show. Ask me to make a new one.</p>;
  if (!share) return null;
  const until = new Date(share.expiresAt).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
  return (
    <figure className="ag-qr">
      <QRCodeSVG value={appUrl(share.url)} size={168} marginSize={2} level="M" />
      <figcaption>Shows {share.scope === "full" ? "all records" : share.scope === "labs" ? "lab reports" : "prescriptions"}. Works until {until}.</figcaption>
    </figure>
  );
}
