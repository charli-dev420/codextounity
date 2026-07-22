import { spawn, spawnSync } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import { appendFileSync, closeSync, copyFileSync, existsSync, mkdirSync, openSync, readFileSync, readSync, readdirSync, statSync, unlinkSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const pluginRoot = path.resolve(__dirname, "..");
const manifestPath = existsSync(path.join(pluginRoot, ".codex-plugin", "plugin.json"))
  ? path.join(pluginRoot, ".codex-plugin", "plugin.json")
  : path.join(pluginRoot, "plugin.json");
const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
const widgetUri = "ui://codex-unity-comfyui-pipeline/asset-factory.html";
const activeJobs = new Map();
const MAX_LOG_BYTES = 256 * 1024;
const LOG_TAIL_BYTES = 6000;
const JOB_ID_PATTERN = /^\d{10,17}_[A-Za-z0-9_.-]{1,160}$/;
const TERMINAL_JOB_STATES = new Set(["planned", "review_needed", "generated", "adjusted", "unity_ready", "failed", "cancelled", "cancel_rejected"]);

const profilesDir = path.join(pluginRoot, "configs", "asset-profiles");
const validFitAxes = new Set(["contain", "x", "y", "z"]);
const finalTools = [
  "open_asset_factory",
  "plan_asset",
  "plan_reference_image",
  "register_reference_image",
  "validate_reference_image",
  "run_asset_pipeline",
  "start_asset_pipeline_job",
  "job_status",
  "add_pipeline_instruction",
  "cancel_pipeline_job",
  "adjust_generated_asset",
  "import_asset_to_unity",
  "install_unity_template",
  "plan_character_attachments",
  "create_character_attachment_manifest",
  "update_character_attachment_slot",
  "list_character_attachment_slots",
  "export_unity_socket_prefab_data",
  "validate_character_attachment_manifest",
];

const tools = [
  t("open_asset_factory", "Open Asset Factory", "Open the local Asset Factory app.", s({ defaultUnityProject: p(), defaultWorkDir: p() }), true, { "openai/outputTemplate": widgetUri }),
  t("plan_asset", "Plan Asset", "Plan an asset with a reusable profile, bounds, budgets, pivot and Unity category.", s({ workDir: p(), assetName: p(), profile: p(), subProfile: p(), assetType: p(), description: p(), style: p(), targetWidth: n(), targetHeight: n(), targetDepth: n(), mobileBudget: e(["low", "medium", "high"]), fitAxis: e(["auto", "contain", "x", "y", "z"]) }, ["assetName", "description"]), true),
  t("plan_reference_image", "Plan Reference Image", "Create the reference-image brief before image generation.", s({ assetName: p(), profile: p(), description: p(), style: p(), view: p(), background: p(), seed: i() }, ["assetName", "description"]), true),
  t("register_reference_image", "Register Reference Image", "Register or copy a reference image into the work folder.", s({ workDir: p(), assetName: p(), imagePath: p(), source: e(["codex", "user", "unity", "manual"]), prompt: p(), copyIntoWorkDir: b() }, ["workDir", "assetName", "imagePath"])),
  t("validate_reference_image", "Validate Reference Image", "Validate local reference image readiness before TRELLIS2.", s({ imagePath: p(), expectedObject: p(), profile: p(), force: b() }, ["imagePath"]), true),
  t("run_asset_pipeline", "Run Asset Pipeline", "Run the foreground local image-to-3D pipeline.", pipelineSchema(["assetName", "referenceImagePath", "workDir"])),
  t("start_asset_pipeline_job", "Start Asset Pipeline Job", "Start a persistent monitorable job with events, logs, instructions and artifacts.", pipelineSchema(["assetName", "workDir"])),
  t("job_status", "Job Status", "Inspect a persistent job after restart and report state, warnings, artifacts and next actions.", s({ workDir: p(), jobId: p(), includeLogs: b() }, ["workDir"]), true),
  t("add_pipeline_instruction", "Add Pipeline Instruction", "Append a timestamped user/Codex/manual runtime instruction to a job.", s({ workDir: p(), jobId: p(), instruction: p(), author: e(["user", "codex", "manual"]) }, ["workDir", "instruction"])),
  t("cancel_pipeline_job", "Cancel Pipeline Job", "Cancel an active local pipeline process and persist cancelled state.", s({ workDir: p(), jobId: p() }, ["jobId"]), false, {}, true),
  t("adjust_generated_asset", "Adjust Generated Asset", "Correct GLB bounds, pivot, rotation, uniform scale, axis remap and offset without rerunning TRELLIS2.", s({ inputMesh: p(), outputMesh: p(), profile: p(), subProfile: p(), rotateEuler: p(), scale: p(), offset: p(), targetBounds: p(), fitAxis: e(["contain", "x", "y", "z"]), pivot: e(["bottom-center", "center", "origin", "custom", "keep"]), axisRemap: p(), customPivot: p(), tolerance: n(), report: p() }, ["inputMesh", "outputMesh"])),
  t("import_asset_to_unity", "Import Asset To Unity", "Create Unity import manifests and copy a Unity-ready mesh.", s({ meshPath: p(), unityProject: p(), assetId: p(), referenceImagePath: p(), unitySubdir: p(), normalizationReport: p(), characterAttachments: p(), dryRun: b() }, ["meshPath", "unityProject"])),
  t("install_unity_template", "Install Unity Template", "Install or refresh the Unity editor template.", s({ unityProject: p(), force: b() }, ["unityProject"])),
  t("plan_character_attachments", "Plan Character Attachments", "Plan stable equipment sockets by characterId and slotId.", s({ characterId: p(), rigName: p(), equipmentKinds: a(), animationUse: p() }, ["characterId"]), true),
  t("create_character_attachment_manifest", "Create Character Attachment Manifest", "Create a Unity-readable attachment manifest.", s({ characterId: p(), rigName: p(), outPath: p(), slots: a(), notes: p() }, ["characterId", "outPath"])),
  t("update_character_attachment_slot", "Update Character Attachment Slot", "Create or update a slot in an attachment manifest.", s({ manifestPath: p(), slotId: p(), bone: p(), position: p(), rotationEuler: p(), scale: p(), equipmentCategory: p(), previewPose: p(), notes: p() }, ["manifestPath", "slotId"])),
  t("list_character_attachment_slots", "List Character Attachment Slots", "List slots from a character attachment manifest.", s({ manifestPath: p() }, ["manifestPath"]), true),
  t("export_unity_socket_prefab_data", "Export Unity Socket Prefab Data", "Export socket prefab data JSON for Unity import.", s({ manifestPath: p(), outPath: p() }, ["manifestPath", "outPath"])),
  t("validate_character_attachment_manifest", "Validate Character Attachment Manifest", "Validate character equipment sockets and transforms.", s({ manifestPath: p() }, ["manifestPath"]), true),
];

function p() { return { type: "string" }; }
function n() { return { type: "number" }; }
function i() { return { type: "integer" }; }
function b() { return { type: "boolean" }; }
function a() { return { type: "array", items: { type: "string" } }; }
function e(values) { return { type: "string", enum: values }; }
function s(properties, required = []) { return { type: "object", required, properties, additionalProperties: false }; }
function t(name, title, description, inputSchema, readOnly = false, meta = {}, destructive = false) {
  return { name, title, description, inputSchema, annotations: { readOnlyHint: readOnly, destructiveHint: destructive, openWorldHint: !readOnly }, ...(Object.keys(meta).length ? { _meta: meta } : {}) };
}
function pipelineSchema(required) {
  return s({
    assetName: p(), profile: p(), subProfile: p(), referenceImagePath: p(), workDir: p(), targetWidth: n(), targetHeight: n(), targetDepth: n(),
    unityProject: p(), unitySubdir: p(), comfyServer: p(), workflow: e(["simple", "low-poly", "mesh-only-hq", "mesh-with-texturing", "mesh-with-texturing-hq"]),
    seed: i(), targetFaces: i(), textureSize: i(), maxViews: i(), dryRun: b(), skipGeneration: b(), forceReference: b(),
    pivot: e(["bottom-center", "center", "origin", "custom", "keep"]), fitAxis: e(["auto", "contain", "x", "y", "z"]), rotateEuler: p(), scale: p(), offset: p(), axisRemap: p(), customPivot: p(), tolerance: n(),
  }, required);
}
function respond(id, result) { process.stdout.write(`${JSON.stringify({ jsonrpc: "2.0", id, result })}\n`); }
function fail(id, code, message, data = null) { process.stdout.write(`${JSON.stringify({ jsonrpc: "2.0", id, error: { code, message, ...(data ? { data } : {}) } })}\n`); }
function result(data, text, meta = {}) { return { structuredContent: data, content: [{ type: "text", text }], _meta: meta }; }
function now() { return new Date().toISOString(); }
function safe(v) { return String(v || "asset").replace(/[^a-z0-9_.-]+/gi, "_").replace(/^_+|_+$/g, "") || "asset"; }
function readJson(file, fallback = null) { try { return JSON.parse(readFileSync(file, "utf8")); } catch { return fallback; } }
function writeJson(file, value) { mkdirSync(path.dirname(file), { recursive: true }); writeFileSync(file, JSON.stringify(value, null, 2), "utf8"); }
function appendJsonl(file, value) {
  mkdirSync(path.dirname(file), { recursive: true });
  appendFileSync(file, `${JSON.stringify(value)}\n`, "utf8");
  if (statSync(file).size <= MAX_LOG_BYTES) return;
  const text = readFileSync(file, "utf8").slice(-MAX_LOG_BYTES);
  const firstLineEnd = text.indexOf("\n");
  const tail = firstLineEnd >= 0 ? text.slice(firstLineEnd + 1) : "";
  const marker = { at: now(), type: "log_truncated", maxBytes: MAX_LOG_BYTES };
  writeFileSync(file, `${JSON.stringify(marker)}\n${tail}`, "utf8");
}
function toolError(code, message, details = {}) {
  const error = new Error(message);
  error.code = code;
  error.details = details;
  return error;
}
function formatToolError(error) {
  return {
    code: error?.code || "tool_error",
    message: error?.message || String(error),
    details: error?.details || {},
    stack: error?.stack || "",
  };
}
function hashCommand(command) {
  return createHash("sha256").update(JSON.stringify(command || [])).digest("hex");
}
function normalizeSearchText(value) {
  return String(value || "").toLowerCase().replace(/\//g, "\\").replace(/"/g, "");
}
function containsPathFragment(text, expectedPath) {
  return normalizeSearchText(text).includes(normalizeSearchText(path.resolve(expectedPath)));
}
function isPathInside(child, parent) {
  const relative = path.relative(path.resolve(parent), path.resolve(child));
  return relative === "" || (!!relative && !relative.startsWith("..") && !path.isAbsolute(relative));
}
function validateUnityProjectRoot(value) {
  if (!value) throw toolError("unity_project_missing", "unityProject is required for Unity import.");
  const root = path.resolve(value);
  const assetsRoot = path.join(root, "Assets");
  if (!existsSync(assetsRoot)) throw toolError("unity_project_invalid", "Unity project must contain an Assets folder.", { unityProject: root, expectedAssets: assetsRoot });
  return { root, assetsRoot };
}
function validateUnitySubdir(unityProject, unitySubdir) {
  const { root, assetsRoot } = validateUnityProjectRoot(unityProject);
  const normalized = String(unitySubdir || "Assets/AIAssetPipeline/Generated/UnityReady").replace(/\\/g, "/").replace(/^\/+|\/+$/g, "");
  if (!normalized.startsWith("Assets/")) throw toolError("unity_subdir_invalid", "unitySubdir must start with Assets/.", { unitySubdir: normalized });
  if (normalized.split("/").includes("..")) throw toolError("unity_subdir_traversal", "unitySubdir cannot contain '..'.", { unitySubdir: normalized });
  const targetDir = path.resolve(root, normalized);
  if (!isPathInside(targetDir, assetsRoot)) throw toolError("unity_import_outside_project", "Unity import path resolves outside the project Assets folder.", { unityProject: root, unitySubdir: normalized, targetDir });
  return { root, assetsRoot, unitySubdir: normalized, targetDir };
}
function appendBoundedLog(file, chunk, maxBytes = MAX_LOG_BYTES) {
  mkdirSync(path.dirname(file), { recursive: true });
  appendFileSync(file, chunk, "utf8");
  const size = statSync(file).size;
  if (size <= maxBytes) return { bytes: Buffer.byteLength(chunk), truncated: false, size };
  const tail = readFileSync(file, "utf8").slice(-maxBytes);
  const marker = `[log truncated to ${maxBytes} bytes at ${now()}]\n`;
  writeFileSync(file, marker + tail.slice(Math.max(0, tail.length - maxBytes + marker.length)), "utf8");
  return { bytes: Buffer.byteLength(chunk), truncated: true, size: statSync(file).size };
}
function limitText(value, max = 20000) {
  const text = String(value || "");
  return text.length <= max ? text : text.slice(-max);
}
function redactLogText(value) {
  return String(value || "")
    .replace(/\bsk-[A-Za-z0-9_-]{12,}\b/g, "<REDACTED_TOKEN>")
    .replace(/authorization:\s*bearer\s+[^\s]+/gi, "Authorization: Bearer <REDACTED>")
    .replace(/\b(api[_-]?key|token|secret)\b\s*[=:]\s*[^\s]+/gi, "$1=<REDACTED>")
    .replace(/[A-Z]:[\\/]+Users[\\/]+[^\\/ \r\n]+/g, "<USER_HOME>");
}
function classifyProcessFailure(command, exitCode, stderr = "", errorCode = "") {
  if (exitCode === 0) return null;
  const haystack = `${errorCode}\n${stderr}`.toLowerCase();
  if (errorCode === "ENOENT" || haystack.includes("enoent")) return { code: "executable_missing", message: `Executable not found: ${command?.[0] || "unknown"}` };
  if (errorCode === "EACCES" || haystack.includes("permission denied") || haystack.includes("access is denied")) return { code: "permission_denied", message: "The command was blocked by local permissions." };
  if (haystack.includes("eaddrinuse") || haystack.includes("address already in use") || haystack.includes("port is already allocated")) return { code: "port_busy", message: "A required local port is already in use." };
  return { code: "command_failed", message: `Command exited with code ${exitCode ?? 1}.` };
}
function acquireJobLock(dir, name) {
  const file = path.join(dir, `${name}.lock`);
  try {
    writeFileSync(file, JSON.stringify({ at: now(), pid: process.pid }), { encoding: "utf8", flag: "wx" });
    return { acquired: true, file };
  } catch (error) {
    return { acquired: false, file, error: String(error?.message || error) };
  }
}
function releaseJobLock(lock) {
  if (!lock?.acquired) return;
  try { unlinkSync(lock.file); } catch {}
}
function loadProfiles() {
  const out = {};
  if (existsSync(profilesDir)) for (const file of readdirSync(profilesDir).filter((x) => x.endsWith(".json"))) out[path.basename(file, ".json")] = readJson(path.join(profilesDir, file), {});
  return out;
}
function normalizeAlias(value) {
  return String(value || "").toLowerCase().trim().replace(/[-\s]+/g, "_");
}
function subProfileEntries(data) {
  return Object.entries(data?.subProfiles || {}).filter(([, sub]) => sub && typeof sub === "object");
}
function aliasesForSubProfile(subId, sub) {
  return [subId, sub.displayName, ...(Array.isArray(sub.aliases) ? sub.aliases : [])].map(normalizeAlias).filter(Boolean);
}
function subProfileFor(data, requested = "", description = "", fallback = "") {
  const exact = normalizeAlias(requested || fallback);
  for (const [subId, sub] of subProfileEntries(data)) {
    if (exact && aliasesForSubProfile(subId, sub).includes(exact)) return { name: subId, data: sub, reason: exact === normalizeAlias(subId) ? "explicit-subProfile" : `subProfile-alias:${exact}` };
  }
  const haystack = normalizeSearchText(description || "");
  let best = null;
  for (const [subId, sub] of subProfileEntries(data)) {
    for (const alias of aliasesForSubProfile(subId, sub)) {
      if (!alias) continue;
      const textAlias = alias.replace(/_/g, " ");
      const index = haystack.indexOf(textAlias);
      if (index < 0) continue;
      if (!best || index < best.index || (index === best.index && alias.length > best.alias.length)) best = { name: subId, data: sub, alias, index };
    }
  }
  return best ? { name: best.name, data: best.data, reason: `description-subProfile:${best.alias}` } : { name: "", data: null, reason: "base-profile" };
}
function profileFor(name, description = "") {
  const all = loadProfiles();
  const requested = String(name || "").toLowerCase().trim();
  const haystack = `${requested} ${description || ""}`.toLowerCase();
  if (requested && all[requested]) return { name: requested, data: all[requested], reason: "explicit-profile" };
  for (const [profileId, data] of Object.entries(all)) {
    const aliases = Array.isArray(data.aliases) ? data.aliases : [profileId];
    if (aliases.map((a) => String(a).toLowerCase()).includes(requested)) return { name: profileId, data, reason: `alias:${requested}` };
  }
  for (const [profileId, data] of Object.entries(all)) {
    const sub = subProfileFor(data, requested);
    if (sub.name) return { name: profileId, data, reason: `subProfile:${sub.name}`, subProfile: sub.name };
  }
  let best = null;
  for (const [profileId, data] of Object.entries(all)) {
    const aliases = Array.isArray(data.aliases) ? data.aliases : [profileId];
    for (const aliasValue of aliases) {
      const alias = String(aliasValue).toLowerCase().trim();
      if (!alias) continue;
      const index = haystack.indexOf(alias);
      if (index < 0) continue;
      const before = index === 0 ? " " : haystack[index - 1];
      const after = index + alias.length >= haystack.length ? " " : haystack[index + alias.length];
      const boundary = /[^a-z0-9_]/i.test(before) && /[^a-z0-9_]/i.test(after);
      if (!boundary && !alias.includes(" ")) continue;
      if (!best || index < best.index || (index === best.index && alias.length > best.alias.length)) best = { profileId, data, alias, index };
    }
    for (const [subId, sub] of subProfileEntries(data)) {
      for (const alias of aliasesForSubProfile(subId, sub)) {
        const textAlias = alias.replace(/_/g, " ");
        const index = haystack.indexOf(textAlias);
        if (index < 0) continue;
        if (!best || index < best.index || (index === best.index && alias.length > best.alias.length)) best = { profileId, data, alias, index, subProfile: subId };
      }
    }
  }
  if (best) return { name: best.profileId, data: best.data, reason: `description-alias:${best.alias}`, subProfile: best.subProfile || "" };
  return { name: "prop", data: all.prop || {}, reason: "fallback-prop" };
}
function normalizationDefaults(profileId, data, sub = null) {
  const fallback = { fitMode: "preserve-aspect", targetBoundsMode: "max-envelope", allowNonUniformScale: false, scale: 1, fitAxis: "contain" };
  const merged = { ...fallback, ...(data.normalizationDefaults || {}) };
  if (sub?.data) Object.assign(merged, sub.data.normalizationDefaults || {});
  if (!validFitAxes.has(String(merged.fitAxis || ""))) merged.fitAxis = "contain";
  return merged;
}
function targetBoundsSource(profile, sub = null) {
  return sub?.data?.targetBounds || profile?.targetBounds || {};
}
function availableProfileSummaries() {
  return Object.entries(loadProfiles()).map(([profileId, data]) => ({
    profileId,
    displayName: data.displayName || profileId,
    aliases: data.aliases || [profileId],
    targetBounds: data.targetBounds,
    normalizationDefaults: normalizationDefaults(profileId, data),
    subProfiles: Object.fromEntries(subProfileEntries(data).map(([subId, sub]) => [subId, {
      displayName: sub.displayName || subId,
      aliases: sub.aliases || [subId],
      targetBounds: sub.targetBounds,
      fitAxis: normalizationDefaults(profileId, data, { name: subId, data: sub }).fitAxis,
      unityCategory: sub.unityCategory || data.unityCategory,
    }])),
    faceBudget: data.faceBudget,
    textureSize: data.textureSize,
    pivotMode: data.pivotMode,
    fitAxis: normalizationDefaults(profileId, data).fitAxis,
    unityCategory: data.unityCategory,
  }));
}
function bounds(args, profile, sub = null) {
  const d = targetBoundsSource(profile, sub);
  return { width: Number(args.targetWidth ?? d.x ?? 1), height: Number(args.targetHeight ?? d.y ?? 1), depth: Number(args.targetDepth ?? d.z ?? 1) };
}
function fitAxisFor(profileId, profile, sub, requested) {
  const value = String(requested || "auto").toLowerCase();
  if (value && value !== "auto") return value;
  return normalizationDefaults(profileId, profile || {}, sub).fitAxis;
}
function jobRoot(workDir) { return path.join(path.resolve(workDir), ".codex_asset_jobs"); }
function jobDir(workDir, jobId) { return path.join(jobRoot(workDir), jobId); }
function validateJobId(jobId) {
  const id = String(jobId || "");
  if (!JOB_ID_PATTERN.test(id)) throw toolError("invalid_job_id", "jobId must be 'latest' or a generated asset job id.", { jobId: id });
  return id;
}
function resolveJobId(workDir, requested) {
  if (!requested || requested === "latest") return latestJobId(workDir);
  return validateJobId(requested);
}
function resolveJobDir(workDir, jobId) {
  const root = jobRoot(workDir);
  const dir = path.resolve(root, validateJobId(jobId));
  if (!isPathInside(dir, root)) throw toolError("invalid_job_path", "Resolved job path escaped the jobs root.", { jobId, jobsRoot: root, jobDir: dir });
  return dir;
}
function latestJobId(workDir) {
  const root = jobRoot(workDir);
  if (!existsSync(root)) return "";
  const dirs = readdirSync(root).map((x) => path.join(root, x)).filter((x) => statSync(x).isDirectory());
  return dirs.length ? path.basename(dirs.sort((x, y) => statSync(y).mtimeMs - statSync(x).mtimeMs)[0]) : "";
}
function appendEvent(dir, type, payload = {}) { appendJsonl(path.join(dir, "events.jsonl"), { at: now(), type, ...payload }); }
function ensureJobFiles(dir) {
  mkdirSync(dir, { recursive: true });
  for (const name of ["events.jsonl", "instructions.jsonl", "stdout.log", "stderr.log"]) {
    const file = path.join(dir, name);
    if (!existsSync(file)) writeFileSync(file, "", "utf8");
  }
  const artifactsPath = path.join(dir, "artifacts.json");
  if (!existsSync(artifactsPath)) writeJson(artifactsPath, { artifacts: [] });
}
function isPidAlive(pid) {
  const value = Number(pid);
  if (!Number.isFinite(value) || value <= 0) return false;
  try { process.kill(value, 0); return true; } catch { return false; }
}
function getProcessInfo(pid) {
  const value = Number(pid);
  if (!Number.isFinite(value) || value <= 0) return { found: false, error: "invalid pid" };
  if (process.platform === "win32") {
    const script = `$p=Get-CimInstance Win32_Process -Filter "ProcessId=${value}" -ErrorAction SilentlyContinue; if ($p) { [pscustomobject]@{ processId=$p.ProcessId; executablePath=$p.ExecutablePath; commandLine=$p.CommandLine } | ConvertTo-Json -Compress }`;
    const completed = spawnSync("powershell", ["-NoProfile", "-Command", script], { encoding: "utf8", windowsHide: true, timeout: 5000 });
    if (completed.status === 0 && completed.stdout.trim()) {
      try { return { found: true, ...JSON.parse(completed.stdout) }; } catch (error) { return { found: false, error: `process info JSON parse failed: ${error}` }; }
    }
    return { found: false, error: completed.stderr || completed.error?.message || "process not found" };
  }
  const completed = spawnSync("ps", ["-p", String(value), "-o", "pid=", "-o", "command="], { encoding: "utf8", timeout: 5000 });
  if (completed.status === 0 && completed.stdout.trim()) return { found: true, processId: value, commandLine: completed.stdout.trim(), executablePath: "" };
  return { found: false, error: completed.stderr || completed.error?.message || "process not found" };
}
function persistedProcessIdentity(job) {
  const fileIdentity = job?.jobDir ? readJson(path.join(job.jobDir, "process_identity.json"), null) : null;
  return fileIdentity || job?.processIdentity || null;
}
function verifyPersistedJobProcess(job) {
  const identity = persistedProcessIdentity(job);
  const pid = Number(job?.pid || identity?.pid);
  if (!Number.isFinite(pid) || pid <= 0) return { trusted: false, pid: job?.pid || null, alive: false, reason: "missing_pid" };
  const alive = isPidAlive(pid);
  if (!alive) return { trusted: false, pid, alive: false, reason: "pid_not_running" };
  if (!identity) return { trusted: false, pid, alive: true, reason: "missing_process_identity" };
  if (job?.owner?.marker && identity.marker !== job.owner.marker) return { trusted: false, pid, alive: true, reason: "marker_mismatch" };
  if (identity.pluginRoot && path.resolve(identity.pluginRoot) !== pluginRoot) return { trusted: false, pid, alive: true, reason: "plugin_root_mismatch" };
  if (job?.command && identity.commandHash !== hashCommand(job.command)) return { trusted: false, pid, alive: true, reason: "command_hash_mismatch" };
  const info = getProcessInfo(pid);
  if (!info.found || !info.commandLine) return { trusted: false, pid, alive: true, reason: "process_info_unavailable", processInfo: info };
  const expectedScript = path.join(pluginRoot, "scripts", "generate_asset.py");
  if (!containsPathFragment(info.commandLine, expectedScript)) return { trusted: false, pid, alive: true, reason: "command_line_script_mismatch", processInfo: info };
  if (job?.runWorkDir && !containsPathFragment(info.commandLine, job.runWorkDir)) return { trusted: false, pid, alive: true, reason: "command_line_workdir_mismatch", processInfo: info };
  return { trusted: true, pid, alive: true, reason: "matched_command_line", processInfo: info };
}
function tryKillPid(pid) {
  const value = Number(pid);
  if (!Number.isFinite(value) || value <= 0) return { sent: false, error: "invalid pid" };
  try { process.kill(value); return { sent: true }; } catch (error) { return { sent: false, error: String(error?.message || error) }; }
}
function createJob(args, state = "planned") {
  const jobId = `${Date.now()}_${safe(args.assetName)}`;
  const dir = jobDir(args.workDir, jobId);
  ensureJobFiles(dir);
  const job = { jobId, assetName: args.assetName, profile: args.profile || "", state, status: state, createdAt: now(), updatedAt: now(), workDir: path.resolve(args.workDir), jobDir: dir, runWorkDir: path.join(dir, "work"), args, owner: { pluginRoot, serverPid: process.pid, marker: randomUUID() } };
  writeJson(path.join(dir, "job.json"), job);
  writeJson(path.join(dir, "artifacts.json"), { artifacts: [] });
  appendEvent(dir, "job_created", { state });
  return job;
}
function updateJob(job, patch) {
  const next = { ...job, ...patch, updatedAt: now() };
  next.status = next.state;
  writeJson(path.join(next.jobDir, "job.json"), next);
  return next;
}
function fileTail(file, max = LOG_TAIL_BYTES) {
  if (!existsSync(file)) return "";
  const size = statSync(file).size;
  const length = Math.min(size, max);
  const buffer = Buffer.alloc(length);
  const handle = openSync(file, "r");
  try {
    readSync(handle, buffer, 0, length, Math.max(0, size - length));
  } finally {
    closeSync(handle);
  }
  const prefix = size > max ? `[tail truncated to ${max} bytes]\n` : "";
  return redactLogText(prefix + buffer.toString("utf8"));
}
function artifactKind(file) {
  const ext = path.extname(file).toLowerCase();
  if ([".png", ".jpg", ".jpeg", ".webp"].includes(ext)) return "image";
  if ([".glb", ".gltf", ".obj", ".fbx", ".dae", ".stl"].includes(ext)) return "mesh";
  if ([".json", ".jsonl", ".log"].includes(ext)) return "manifest_or_log";
  return "other";
}
function walk(dir, rows, limit, makeRow) {
  if (!existsSync(dir) || rows.length >= limit) return;
  for (const name of readdirSync(dir)) {
    if (rows.length >= limit) break;
    const full = path.join(dir, name);
    const stat = statSync(full);
    if (stat.isDirectory()) walk(full, rows, limit, makeRow);
    else rows.push(makeRow(full, stat));
  }
}
function scanArtifacts(dir) {
  const rows = [];
  walk(dir, rows, 500, (file, stat) => ({ path: file, bytes: stat.size, modifiedAt: stat.mtime.toISOString(), kind: artifactKind(file) }));
  return rows.filter((x) => x.kind !== "other");
}

function planAsset(args) {
  const selected = profileFor(args.profile || args.assetType, args.description);
  const sub = subProfileFor(selected.data, args.subProfile, args.description, selected.subProfile);
  const bnd = bounds(args, selected.data, sub);
  const defaults = normalizationDefaults(selected.name, selected.data, sub);
  const prompt = [
    `Create one ${sub.name || selected.name} reference image for image-to-3D reconstruction.`,
    `Subject: ${args.description}`,
    args.style ? `Style: ${args.style}` : "Style: project-defined game asset style.",
    ...(selected.data.promptRules || []),
    "Camera: 3/4 slightly top-down unless profile or user says otherwise.",
    "Background: flat uniform plain background, no floor plane, no shadow.",
    "Do not draw text, dimension marks, rulers, labels, UI, or multiple objects.",
  ].join("\n");
  return result({ assetName: args.assetName, profile: selected.name, subProfile: sub.name, profileReason: selected.reason, subProfileReason: sub.reason, displayName: sub.data?.displayName || selected.data.displayName || selected.name, referencePrompt: prompt, negativePromptRules: selected.data.negativePromptRules || [], targetBounds: bnd, faceBudget: selected.data.faceBudget || 9000, textureSize: selected.data.textureSize || 1024, pivotMode: selected.data.pivotMode || "bottom-center", unityCategory: sub.data?.unityCategory || selected.data.unityCategory || "props", normalizationControls: { fitMode: defaults.fitMode || "preserve-aspect", targetBoundsMode: defaults.targetBoundsMode || "max-envelope", allowNonUniformScale: defaults.allowNonUniformScale === false, fitAxis: fitAxisFor(selected.name, selected.data, sub, args.fitAxis), pivot: selected.data.pivotMode || "bottom-center", axisRemap: "x,y,z", uniformScale: String(defaults.scale ?? 1), tolerance: (selected.data.validationRules || {}).boundsTolerance || 0.002 }, generationDefaults: selected.data.generationDefaults || {}, importDefaults: selected.data.importDefaults || {}, validationRules: selected.data.validationRules || {}, availableProfiles: availableProfileSummaries(), nextActions: ["plan_reference_image", "register_reference_image", "validate_reference_image", "start_asset_pipeline_job"] }, `Planned ${args.assetName} with profile ${selected.name}${sub.name ? `/${sub.name}` : ""}.`);
}
function planReferenceImage(args) {
  const selected = profileFor(args.profile, args.description);
  const sub = subProfileFor(selected.data, args.subProfile, args.description, selected.subProfile);
  const prompt = [
    `Reference image for ${args.assetName}.`,
    `Object: ${args.description}`,
    args.style ? `Style: ${args.style}` : "Style: coherent with project assets.",
    ...(selected.data.promptRules || []),
    `View: ${args.view || "3/4 top-down, entire object visible"}.`,
    `Background: ${args.background || "plain uniform matte background"}.`,
    "Lighting: even, no cast shadow, no text, no measurements, one object only.",
  ].join("\n");
  return result({ assetName: args.assetName, profile: selected.name, subProfile: sub.name, prompt, seed: args.seed ?? 2146628683, nextAction: "Create the image, save it locally, then call register_reference_image." }, `Reference image plan ready for ${args.assetName}.`);
}
function validateReferenceImageData(imagePath, expectedObject, force) {
  const script = path.join(pluginRoot, "scripts", "validate_reference_image.py");
  if (existsSync(script)) {
    const command = [script, "--image", imagePath, "--expected-object", expectedObject || "asset"];
    if (force) command.push("--force");
    const completed = spawnSync("python", ["-B", ...command], { cwd: pluginRoot, encoding: "utf8", windowsHide: true });
    if (completed.stdout) {
      try {
        const parsed = JSON.parse(completed.stdout);
        parsed.validator = { command: ["python", "-B", ...command], exitCode: completed.status ?? 0, stderr: completed.stderr || "" };
        return parsed;
      } catch (error) {
        return { imagePath, expectedObject, valid: false, forced: false, errors: [`reference validator JSON parse failed: ${error}`], warnings: [completed.stderr || completed.stdout], imageInfo: null };
      }
    }
    if (completed.error) return { imagePath, expectedObject, valid: !!force, forced: !!force, errors: [`reference validator failed: ${completed.error}`], warnings: [], imageInfo: null };
  }
  const errors = [];
  const warnings = [];
  if (!existsSync(imagePath)) errors.push(`missing file: ${imagePath}`);
  const ext = path.extname(imagePath).toLowerCase();
  if (![".png", ".jpg", ".jpeg", ".webp"].includes(ext)) errors.push(`unsupported image format: ${ext || "none"}`);
  let imageInfo = null;
  if (existsSync(imagePath)) imageInfo = readImageInfo(imagePath);
  warnings.push("Fallback validation only; visual review still required.");
  return { imagePath, expectedObject, imageInfo, valid: force || errors.length === 0, forced: force, errors, warnings };
}
function readImageInfo(file) {
  try {
    const x = readFileSync(file);
    if (x.length > 24 && x.toString("ascii", 1, 4) === "PNG") return { type: "png", width: x.readUInt32BE(16), height: x.readUInt32BE(20) };
    if (x.length > 10 && x[0] === 0xff && x[1] === 0xd8) {
      let i = 2;
      while (i + 9 < x.length) {
        if (x[i] !== 0xff) break;
        const marker = x[i + 1], len = x.readUInt16BE(i + 2);
        if ([0xc0, 0xc1, 0xc2, 0xc3].includes(marker)) return { type: "jpeg", width: x.readUInt16BE(i + 7), height: x.readUInt16BE(i + 5) };
        i += 2 + len;
      }
    }
    return { type: path.extname(file).slice(1) || "unknown" };
  } catch {
    return null;
  }
}
function validateReferenceImage(args) {
  const data = validateReferenceImageData(path.resolve(args.imagePath), args.expectedObject || args.profile || "asset", !!args.force);
  return result(data, data.valid ? "Reference image is usable." : "Reference image needs correction before TRELLIS2.");
}
function registerReferenceImage(args) {
  const source = path.resolve(args.imagePath);
  if (!existsSync(source)) throw new Error(`Reference image not found: ${source}`);
  const referencesDir = path.join(path.resolve(args.workDir), "references");
  mkdirSync(referencesDir, { recursive: true });
  const dest = args.copyIntoWorkDir === false ? source : path.join(referencesDir, `${safe(args.assetName)}${path.extname(source).toLowerCase() || ".png"}`);
  if (dest !== source) copyFileSync(source, dest);
  const validation = validateReferenceImageData(dest, args.assetName, false);
  const manifestPath = path.join(referencesDir, "reference_manifest.json");
  const manifest = readJson(manifestPath, { references: [] });
  manifest.references = (manifest.references || []).filter((x) => x.assetName !== args.assetName);
  manifest.references.push({ assetName: args.assetName, imagePath: dest, originalPath: source, source: args.source || "manual", prompt: args.prompt || "", registeredAt: now(), validation });
  writeJson(manifestPath, manifest);
  return result({ imagePath: dest, manifestPath, validation }, `Registered reference image for ${args.assetName}.`);
}
function buildPipelineCommand(args, job) {
  const selected = profileFor(args.profile, args.description);
  const sub = subProfileFor(selected.data, args.subProfile, args.description, selected.subProfile);
  const bnd = bounds(args, selected.data, sub);
  const pivot = args.pivot || selected.data.pivotMode || "bottom-center";
  const fitAxis = fitAxisFor(selected.name, selected.data, sub, args.fitAxis);
  const tolerance = args.tolerance ?? (selected.data.validationRules || {}).boundsTolerance ?? 0.002;
  const command = [
    "python", "-B", path.join(pluginRoot, "scripts", "generate_asset.py"),
    "--asset-name", args.assetName,
    "--reference-image", args.referenceImagePath || path.join(job?.jobDir || args.workDir, "missing_reference.png"),
    "--work-dir", job?.runWorkDir || args.workDir,
    "--target-width", String(bnd.width),
    "--target-height", String(bnd.height),
    "--target-depth", String(bnd.depth),
    "--asset-profile", selected.name,
    "--profiles-dir", profilesDir,
    "--pivot", pivot,
    "--fit-axis", fitAxis,
    "--rotate-euler", args.rotateEuler || "0,0,0",
    "--scale", args.scale || "1",
    "--offset", args.offset || "0,0,0",
    "--axis-remap", args.axisRemap || "x,y,z",
    "--custom-pivot", args.customPivot || "0,0,0",
    "--tolerance", String(tolerance),
    "--server", args.comfyServer || "http://127.0.0.1:8188",
    "--workflow", args.workflow || "simple",
    "--seed", String(args.seed ?? 2146628683),
    "--target-faces", String(args.targetFaces ?? selected.data.faceBudget ?? 9000),
    "--texture-size", String(args.textureSize ?? selected.data.textureSize ?? 1024),
    "--max-views", String(args.maxViews ?? 4),
  ];
  if (sub.name) command.push("--sub-profile", sub.name);
  if (args.unityProject) command.push("--unity-project", args.unityProject);
  const unitySubdir = args.unitySubdir || selected.data.importDefaults?.unitySubdir;
  if (unitySubdir) command.push("--unity-subdir", unitySubdir);
  if (args.dryRun) command.push("--dry-run");
  if (args.skipGeneration) command.push("--skip-generation");
  return command;
}
async function runAssetPipeline(args) {
  if (!args.dryRun && !args.forceReference) {
    const v = validateReferenceImageData(path.resolve(args.referenceImagePath || ""), args.assetName, false);
    if (!v.valid) return result({ validation: v }, "Reference image rejected before TRELLIS2. Use forceReference to override.");
  }
  const command = buildPipelineCommand(args, { runWorkDir: args.workDir, jobDir: args.workDir });
  if (args.dryRun) {
    const selected = profileFor(args.profile, args.description);
    const sub = subProfileFor(selected.data, args.subProfile, args.description, selected.subProfile);
    return result({ command, dryRun: true, profile: selected.name, subProfile: sub.name }, "Dry-run command planned; no process launched.");
  }
  const out = await runProcess(command, { cwd: pluginRoot });
  return result({ command, exitCode: out.exitCode, stdout: limitText(out.stdout, 10000), stderr: limitText(out.stderr, 10000), structuredError: out.structuredError, workDir: path.resolve(args.workDir) }, out.exitCode === 0 ? `Pipeline completed for ${args.assetName}.` : `Pipeline failed for ${args.assetName}.`);
}
function startAssetPipelineJob(args) {
  const job = createJob(args, "queued");
  const command = buildPipelineCommand(args, job);
  const commandHash = hashCommand(command);
  const selected = profileFor(args.profile, args.description);
  const sub = subProfileFor(selected.data, args.subProfile, args.description, selected.subProfile);
  let saved = updateJob(job, { command, commandHash, profile: selected.name, subProfile: sub.name });
  appendEvent(job.jobDir, "queued", { command });
  if (args.dryRun) {
    saved = updateJob(saved, { state: "planned", endedAt: now(), dryRun: true });
    appendEvent(job.jobDir, "dry_run_planned", { command });
    writeJson(path.join(job.jobDir, "artifacts.json"), { artifacts: scanArtifacts(job.jobDir), command });
    return result({ job: saved, command }, `Dry-run job ${job.jobId} planned and persisted.`);
  }
  if (!args.forceReference) {
    const v = validateReferenceImageData(path.resolve(args.referenceImagePath || ""), args.assetName, false);
    if (!v.valid) {
      const reviewed = updateJob(saved, { state: "review_needed", validation: v });
      appendEvent(job.jobDir, "reference_rejected", v);
      return result({ job: reviewed, validation: v }, "Reference image needs review before TRELLIS2. No process launched.");
    }
  }
  const stdoutPath = path.join(job.jobDir, "stdout.log");
  const stderrPath = path.join(job.jobDir, "stderr.log");
  const child = spawn(command[0], command.slice(1), { cwd: pluginRoot, windowsHide: true });
  const processIdentity = { pid: child.pid, commandHash, marker: saved.owner?.marker || "", pluginRoot, cwd: pluginRoot, runWorkDir: job.runWorkDir, script: path.join(pluginRoot, "scripts", "generate_asset.py"), executable: command[0], startedAt: now() };
  writeJson(path.join(job.jobDir, "process_identity.json"), processIdentity);
  saved = updateJob(saved, { state: "generating", pid: child.pid, startedAt: processIdentity.startedAt, processIdentity });
  appendEvent(job.jobDir, "process_started", { pid: child.pid, commandHash });
  activeJobs.set(job.jobId, { ...saved, child });
  child.stdout.on("data", (chunk) => { const log = appendBoundedLog(stdoutPath, chunk); appendEvent(job.jobDir, "stdout", log); });
  child.stderr.on("data", (chunk) => { const log = appendBoundedLog(stderrPath, chunk); appendEvent(job.jobDir, "stderr", log); });
  child.on("error", (error) => {
    const current = readJson(path.join(job.jobDir, "job.json"), saved);
    const structuredError = classifyProcessFailure(command, 127, String(error), error?.code || "");
    updateJob(current, { state: "failed", endedAt: now(), error: String(error), structuredError });
    appendEvent(job.jobDir, "process_error", { error: String(error), structuredError });
    activeJobs.delete(job.jobId);
  });
  child.on("close", (exitCode) => {
    const current = readJson(path.join(job.jobDir, "job.json"), saved);
    const artifacts = scanArtifacts(job.jobDir);
    writeJson(path.join(job.jobDir, "artifacts.json"), { artifacts });
    if (["cancelling", "cancelled"].includes(current.state)) {
      updateJob(current, { state: "cancelled", exitCode: exitCode ?? null, endedAt: now() });
      appendEvent(job.jobDir, "process_closed", { exitCode, state: "cancelled", artifactCount: artifacts.length });
      activeJobs.delete(job.jobId);
      return;
    }
    const hasUnity = artifacts.some((x) => x.path.includes("UnityReady") || x.path.endsWith("unity_import_manifest.json"));
    const state = exitCode === 0 ? (hasUnity ? "unity_ready" : "generated") : "failed";
    const structuredError = classifyProcessFailure(command, exitCode ?? 1, fileTail(stderrPath));
    updateJob(current, { state, exitCode: exitCode ?? 1, endedAt: now(), ...(structuredError ? { structuredError } : {}) });
    appendEvent(job.jobDir, "process_closed", { exitCode, state, artifactCount: artifacts.length, ...(structuredError ? { structuredError } : {}) });
    activeJobs.delete(job.jobId);
  });
  return result({ jobId: job.jobId, pid: child.pid, state: "generating", command, jobDir: job.jobDir, stdoutPath, stderrPath }, `Started monitorable pipeline job ${job.jobId}.`);
}
function jobStatus(args) {
  const id = resolveJobId(args.workDir, args.jobId || "latest");
  if (!id) return result({ workDir: path.resolve(args.workDir), found: false, jobsRoot: jobRoot(args.workDir) }, "No persistent job found.");
  const dir = resolveJobDir(args.workDir, id);
  if (!existsSync(path.join(dir, "job.json"))) return result({ workDir: path.resolve(args.workDir), jobId: id, found: false, jobsRoot: jobRoot(args.workDir) }, `Job ${id} was not found.`);
  ensureJobFiles(dir);
  const job = readJson(path.join(dir, "job.json"), { jobId: id, state: "unknown", jobDir: dir });
  const artifacts = scanArtifacts(dir);
  writeJson(path.join(dir, "artifacts.json"), { artifacts });
  const warnings = [];
  const active = activeJobs.get(id);
  const verification = job.pid ? (active ? { trusted: true, pid: job.pid, alive: isPidAlive(job.pid), reason: "active_child_in_session" } : verifyPersistedJobProcess(job)) : { trusted: false, pid: null, alive: false, reason: "missing_pid" };
  const processState = { activeInThisSession: activeJobs.has(id), pid: job.pid || null, pidAlive: verification.alive, identityTrusted: verification.trusted, identityReason: verification.reason };
  if (job.state === "generated" && !artifacts.some((x) => x.kind === "mesh")) warnings.push("state says generated but no mesh artifact was found");
  if (job.state === "generating" && job.pid && !processState.activeInThisSession && processState.pidAlive) warnings.push("process is still running but MCP memory was restarted; cancellation can use persisted pid");
  if (job.state === "generating" && job.pid && !processState.pidAlive) warnings.push("job is marked generating but persisted pid is not running");
  if (job.state === "generating" && job.pid && processState.pidAlive && !processState.identityTrusted) warnings.push(`persisted pid is alive but not trusted for cancellation: ${processState.identityReason}`);
  const data = { job, process: processState, warnings, artifacts, nextActions: nextActions(job.state, artifacts), eventsPath: path.join(dir, "events.jsonl"), instructionsPath: path.join(dir, "instructions.jsonl"), stdoutPath: path.join(dir, "stdout.log"), stderrPath: path.join(dir, "stderr.log"), logLimits: { tailBytes: LOG_TAIL_BYTES, maxLogBytes: MAX_LOG_BYTES }, stdoutTail: args.includeLogs ? fileTail(path.join(dir, "stdout.log")) : undefined, stderrTail: args.includeLogs ? fileTail(path.join(dir, "stderr.log")) : undefined };
  return result(data, `Job ${id}: ${job.state || job.status || "unknown"}.`);
}
function nextActions(state, artifacts) {
  if (["planned", "reference_ready"].includes(state)) return ["validate_reference_image", "start_asset_pipeline_job"];
  if (state === "review_needed") return ["register_reference_image", "validate_reference_image", "add_pipeline_instruction"];
  if (state === "generated") return ["adjust_generated_asset", "import_asset_to_unity"];
  if (state === "adjusted") return ["import_asset_to_unity"];
  if (state === "unity_ready") return ["import_asset_to_unity", "add to scene in Unity"];
  if (state === "failed") return ["inspect stderr.log", "add_pipeline_instruction", "retry with adjusted settings"];
  if (state === "cancelled") return ["start a new job"];
  return artifacts.some((x) => x.kind === "mesh") ? ["adjust_generated_asset", "import_asset_to_unity"] : ["plan_reference_image"];
}
function addPipelineInstruction(args) {
  const id = resolveJobId(args.workDir, args.jobId || "latest");
  const dir = id ? resolveJobDir(args.workDir, id) : jobRoot(args.workDir);
  mkdirSync(dir, { recursive: true });
  const entry = { at: now(), author: args.author || "user", instruction: args.instruction };
  appendJsonl(path.join(dir, "instructions.jsonl"), entry);
  appendEvent(dir, "instruction_added", entry);
  return result({ jobId: id || null, instructionsPath: path.join(dir, "instructions.jsonl"), entry }, `Instruction recorded: ${args.instruction}`);
}
function cancelPipelineJob(args) {
  const id = resolveJobId(args.workDir || ".", args.jobId);
  if (!id) return result({ jobId: null, foundActive: false, state: "not_found", kill: { sent: false, source: "none", error: "job not found" } }, "No persistent job found.");
  const active = activeJobs.get(id);
  const dir = args.workDir ? resolveJobDir(args.workDir, id) : active?.jobDir;
  if (!id || (!active && (!dir || !existsSync(path.join(dir, "job.json"))))) {
    return result({ jobId: id || null, foundActive: false, state: "not_found", kill: { sent: false, source: "none", error: "job not found" } }, `Job ${id || "unknown"} was not found.`);
  }
  const lock = dir ? acquireJobLock(dir, "cancel") : { acquired: true };
  if (!lock.acquired) {
    return result({ jobId: id, foundActive: !!active, state: "cancelling", lock }, `Job ${id} is already being cancelled.`);
  }
  let killResult = { sent: false, source: "none" };
  try {
    ensureJobFiles(dir);
    const job = readJson(path.join(dir, "job.json"), { jobId: id, jobDir: dir, state: "unknown" });
    if (TERMINAL_JOB_STATES.has(job.state) || !["queued", "generating", "cancelling"].includes(job.state)) {
      killResult = { sent: false, source: "state", reason: `job is ${job.state || "unknown"}, no live process cancellation required` };
      appendEvent(dir, "cancel_skipped", { by: "tool", kill: killResult });
      activeJobs.delete(id);
      return result({ jobId: id, foundActive: !!active, state: job.state || "unknown", kill: killResult }, `Job ${id} is ${job.state || "unknown"}; no running process was cancelled.`);
    }
    if (job.state === "queued") {
      killResult = { sent: false, source: "state", reason: "job was queued but no process was running" };
      updateJob(job, { state: "cancelled", endedAt: now(), cancel: killResult });
      appendEvent(dir, "cancelled", { by: "tool", kill: killResult });
      activeJobs.delete(id);
      return result({ jobId: id, foundActive: !!active, state: "cancelled", kill: killResult }, `Cancelled queued job ${id}.`);
    }
    updateJob(job, { state: "cancelling", cancelRequestedAt: now() });
    appendEvent(dir, "cancel_requested", { by: "tool" });
    if (active?.child) {
      const sent = active.child.kill();
      killResult = { sent, source: "active-child", ...(sent ? {} : { error: "signal not sent" }) };
    } else {
      const persisted = readJson(path.join(dir, "job.json"), job);
      const verification = verifyPersistedJobProcess(persisted);
      if (verification.trusted) killResult = { ...tryKillPid(verification.pid), source: "persisted-pid", verification };
      else killResult = { sent: false, source: "persisted-pid", error: "persisted pid was not trusted; no signal sent", verification };
    }
    const current = readJson(path.join(dir, "job.json"), job);
    const nextState = killResult.sent ? "cancelled" : "cancel_rejected";
    updateJob(current, { state: nextState, endedAt: now(), cancel: killResult });
    appendEvent(dir, nextState, { by: "tool", kill: killResult });
    if (killResult.sent) activeJobs.delete(id);
    return result({ jobId: id, foundActive: !!active, state: nextState, kill: killResult }, killResult.sent ? `Cancelled job ${id}.` : `Refused to cancel job ${id}: process identity could not be verified.`);
  } finally {
    releaseJobLock(lock);
  }
}
async function adjustGeneratedAsset(args) {
  const command = ["python", "-B", path.join(pluginRoot, "scripts", "normalize_asset_bounds.py"), "--input", args.inputMesh, "--output", args.outputMesh, "--rotate-euler", args.rotateEuler || "0,0,0", "--scale", args.scale || "1", "--offset", args.offset || "0,0,0", "--pivot", args.pivot || "bottom-center"];
  if (args.profile) command.push("--profile", args.profile, "--profiles-dir", profilesDir);
  if (args.subProfile) command.push("--sub-profile", args.subProfile);
  if (args.targetBounds) command.push("--target-bounds", args.targetBounds);
  if (args.fitAxis) command.push("--fit-axis", args.fitAxis);
  if (args.axisRemap) command.push("--axis-remap", args.axisRemap);
  if (args.customPivot) command.push("--custom-pivot", args.customPivot);
  if (args.tolerance !== undefined) command.push("--tolerance", String(args.tolerance));
  if (args.report) command.push("--report", args.report);
  const out = await runProcess(command, { cwd: pluginRoot });
  return result({ command, exitCode: out.exitCode, stdout: limitText(out.stdout, 10000), stderr: limitText(out.stderr, 10000), structuredError: out.structuredError }, out.exitCode === 0 ? "Asset adjustment complete." : "Asset adjustment failed.");
}
async function importAssetToUnity(args) {
  const mesh = path.resolve(args.meshPath);
  if (!existsSync(mesh)) throw new Error(`meshPath not found: ${mesh}`);
  const unity = validateUnitySubdir(args.unityProject, args.unitySubdir || "Assets/AIAssetPipeline/Generated/UnityReady");
  const importDir = path.join(path.dirname(mesh), ".unity_import", safe(args.assetId || path.basename(mesh, path.extname(mesh))));
  const stagedMesh = path.join(importDir, path.basename(mesh));
  const command = ["python", "-B", path.join(pluginRoot, "scripts", "postprocess_generation.py"), "--batch-output-dir", importDir, "--unity-project", unity.root, "--unity-subdir", unity.unitySubdir, "--select", "newest", "--limit", "1", "--asset-id", args.assetId || path.basename(mesh, path.extname(mesh)), "--reference-image", args.referenceImagePath || "", "--workflow-label", "trellis2", "--generation-profile", "CodexAssetFactory", "--validation-profile", "CodexPostGeneration"];
  if (args.normalizationReport) command.push("--normalization-report", args.normalizationReport);
  if (args.characterAttachments) command.push("--character-attachments", args.characterAttachments);
  if (args.dryRun) command.push("--dry-run");
  if (args.dryRun) return result({ command, dryRun: true, exitCode: 0, unityProject: unity.root, unitySubdir: unity.unitySubdir, importDir, stagedMesh }, "Unity import dry-run planned; no files copied.");
  mkdirSync(importDir, { recursive: true });
  if (stagedMesh !== mesh) copyFileSync(mesh, stagedMesh);
  const out = await runProcess(command, { cwd: pluginRoot });
  return result({ command, exitCode: out.exitCode, stdout: limitText(out.stdout, 10000), stderr: limitText(out.stderr, 10000), structuredError: out.structuredError, unityProject: unity.root, unitySubdir: unity.unitySubdir }, out.exitCode === 0 ? "Unity import manifest/copy complete." : "Unity import failed.");
}
async function installUnityTemplate(args) {
  const script = path.join(pluginRoot, "scripts", "install_unity_template.ps1");
  const command = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script, "-UnityProjectRoot", args.unityProject];
  if (args.force) command.push("-Force");
  const out = await runProcess(command, { cwd: pluginRoot });
  return result({ command, exitCode: out.exitCode, stdout: out.stdout, stderr: out.stderr, structuredError: out.structuredError }, out.exitCode === 0 ? "Unity template installed." : "Unity template install failed.");
}
function planCharacterAttachments(args) {
  const kinds = (args.equipmentKinds || []).map((v) => String(v).toLowerCase());
  const slots = new Set(["main_hand", "offhand", "back", "head", "chest", "hips", "belt", "feet", "shoulders"]);
  for (const kind of kinds) {
    if (kind.includes("weapon") || kind.includes("sword") || kind.includes("gun")) slots.add("main_hand");
    if (kind.includes("shield") || kind.includes("torch")) slots.add("offhand");
    if (kind.includes("boot")) slots.add("feet");
    if (kind.includes("pauldron") || kind.includes("shoulder")) slots.add("shoulders");
  }
  return result({ characterId: args.characterId, rigName: args.rigName || "Humanoid", recommendedSlots: Array.from(slots), animationUse: args.animationUse || "general", coordinateSystem: { upAxis: "+Y", forwardAxis: "+Z", rightAxis: "+X", unit: "meter" }, nextAction: "create_character_attachment_manifest" }, `Planned character attachment slots for ${args.characterId}.`);
}
async function characterTool(sub, args, extra) {
  const command = ["python", "-B", path.join(pluginRoot, "scripts", "character_attachment_manifest.py"), sub, ...extra];
  const out = await runProcess(command, { cwd: pluginRoot });
  return result({ command, exitCode: out.exitCode, stdout: out.stdout, stderr: out.stderr, structuredError: out.structuredError }, out.exitCode === 0 ? `Character attachment ${sub} OK.` : `Character attachment ${sub} failed.`);
}
function createCharacterAttachmentManifest(args) {
  const extra = ["--character-id", args.characterId, "--rig-name", args.rigName || "Humanoid", "--out", args.outPath];
  if (Array.isArray(args.slots) && args.slots.length) extra.push("--slots", ...args.slots);
  if (args.notes) extra.push("--notes", args.notes);
  return characterTool("create", args, extra);
}
function validateCharacterAttachmentManifest(args) { return characterTool("validate", args, ["--manifest", args.manifestPath]); }
function listCharacterAttachmentSlots(args) { return characterTool("list", args, ["--manifest", args.manifestPath]); }
function exportUnitySocketPrefabData(args) { return characterTool("export-unity", args, ["--manifest", args.manifestPath, "--out", args.outPath]); }
function updateCharacterAttachmentSlot(args) {
  const extra = ["--manifest", args.manifestPath, "--slot-id", args.slotId];
  for (const [cli, key] of [["--bone", "bone"], ["--position", "position"], ["--rotation-euler", "rotationEuler"], ["--scale", "scale"], ["--equipment-category", "equipmentCategory"], ["--preview-pose", "previewPose"], ["--notes", "notes"]]) {
    if (!args[key]) continue;
    if (["position", "rotationEuler", "scale"].includes(key)) extra.push(`${cli}=${args[key]}`);
    else extra.push(cli, args[key]);
  }
  return characterTool("update", args, extra);
}
function runProcess(command, options) {
  return new Promise((resolve) => {
    const child = spawn(command[0], command.slice(1), { ...options, windowsHide: true });
    let stdout = "", stderr = "";
    child.stdout?.on("data", (x) => { stdout = limitText(stdout + x.toString()); });
    child.stderr?.on("data", (x) => { stderr = limitText(stderr + x.toString()); });
    child.on("error", (error) => {
      const nextStderr = limitText(`${stderr}${String(error)}`);
      resolve({ exitCode: 127, stdout, stderr: nextStderr, structuredError: classifyProcessFailure(command, 127, nextStderr, error?.code || "") });
    });
    child.on("close", (exitCode) => {
      const code = exitCode ?? 1;
      resolve({ exitCode: code, stdout, stderr, structuredError: classifyProcessFailure(command, code, stderr) });
    });
  });
}
function widgetHtml() {
  const widgetPath = path.join(pluginRoot, "mcp", "asset-factory-widget.html");
  try {
    return readFileSync(widgetPath, "utf8");
  } catch (error) {
    return `<!doctype html><html><body><h1>Asset Factory</h1><pre>${String(error)}</pre></body></html>`;
  }
}
async function handle(req) {
  const { id, method, params } = req;
  try {
    if (method === "initialize") return respond(id, { protocolVersion: "2025-06-18", capabilities: { tools: {}, resources: {} }, serverInfo: { name: "codex-unity-comfyui-pipeline", version: manifest.version || "0.2.0" }, instructions: "Asset Factory app for Codex-directed local ComfyUI/TRELLIS2 generation, normalization, Unity import and character sockets." });
    if (method === "notifications/initialized") return;
    if (method === "tools/list") return respond(id, { tools });
    if (method === "resources/list") return respond(id, { resources: [{ uri: widgetUri, name: "asset-factory", title: "Asset Factory", mimeType: "text/html;profile=mcp-app" }] });
    if (method === "resources/read") return respond(id, { contents: [{ uri: widgetUri, mimeType: "text/html;profile=mcp-app", text: widgetHtml() }] });
    if (method !== "tools/call") return fail(id, -32601, `Unknown method: ${method}`);
    const name = params?.name, args = params?.arguments || {};
    if (name === "open_asset_factory") return respond(id, result({ app: "asset-factory", ...args }, "Asset Factory opened.", { "openai/outputTemplate": widgetUri }));
    if (name === "plan_asset") return respond(id, planAsset(args));
    if (name === "plan_reference_image") return respond(id, planReferenceImage(args));
    if (name === "register_reference_image") return respond(id, registerReferenceImage(args));
    if (name === "validate_reference_image") return respond(id, validateReferenceImage(args));
    if (name === "run_asset_pipeline") return respond(id, await runAssetPipeline(args));
    if (name === "start_asset_pipeline_job") return respond(id, startAssetPipelineJob(args));
    if (name === "job_status") return respond(id, jobStatus(args));
    if (name === "add_pipeline_instruction") return respond(id, addPipelineInstruction(args));
    if (name === "cancel_pipeline_job") return respond(id, cancelPipelineJob(args));
    if (name === "adjust_generated_asset") return respond(id, await adjustGeneratedAsset(args));
    if (name === "import_asset_to_unity") return respond(id, await importAssetToUnity(args));
    if (name === "install_unity_template") return respond(id, await installUnityTemplate(args));
    if (name === "plan_character_attachments") return respond(id, planCharacterAttachments(args));
    if (name === "create_character_attachment_manifest") return respond(id, await createCharacterAttachmentManifest(args));
    if (name === "update_character_attachment_slot") return respond(id, await updateCharacterAttachmentSlot(args));
    if (name === "list_character_attachment_slots") return respond(id, await listCharacterAttachmentSlots(args));
    if (name === "export_unity_socket_prefab_data") return respond(id, await exportUnitySocketPrefabData(args));
    if (name === "validate_character_attachment_manifest") return respond(id, await validateCharacterAttachmentManifest(args));
    return fail(id, -32602, `Unknown tool: ${name}`);
  } catch (error) {
    const formatted = formatToolError(error);
    return fail(id, -32000, formatted.message, formatted);
  }
}
let buffer = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => {
  buffer += chunk;
  let index;
  while ((index = buffer.indexOf("\n")) >= 0) {
    const line = buffer.slice(0, index).trim();
    buffer = buffer.slice(index + 1);
    if (!line) continue;
    try { handle(JSON.parse(line)); } catch (error) { fail(null, -32700, error?.message || String(error)); }
  }
});





