// One shape for both agents, so the panel does not care which one it is talking to.
import * as C from "../../api/client.js";

export function apiFor(ctx, patientId) {
  if (ctx.doctor) {
    return {
      ready: C.agentAvailable() && !!patientId,
      chat: (text, conv, fileId) => C.doctorAgentChat(text, patientId, conv, fileId),
      task: C.doctorAgentTask,
      confirm: (id, approve) => C.doctorAgentConfirm(id, patientId, approve),
      upload: (file) => C.doctorAgentUpload(patientId, file),
      download: (f) => C.doctorAgentDownload(patientId, f.fileId, f.name),
      setType: null, // the doctor agent reads a document and tells the doctor when it is unsure
    };
  }
  return { ready: C.agentAvailable(), chat: C.agentChat, task: C.agentTask, confirm: C.agentConfirm, upload: C.agentUploadFile,
           download: (f) => C.agentDownload(f.fileId, f.name), setType: C.agentSetFileType };
}
