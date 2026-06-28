import { spawn, spawnSync } from "node:child_process";
import { appendFileSync, copyFileSync, existsSync, mkdirSync, readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
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

const profilesDir = path.join(pluginRoot, "configs", "asset-profiles");
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
  t("plan_asset", "Plan Asset", "Plan an asset with a reusable profile, bounds, budgets, pivot and Unity category.", s({ workDir: p(), assetName: p(), profile: p(), assetType: p(), description: p(), style: p(), targetWidth: n(), targetHeight: n(), targetDepth: n(), mobileBudget: e(["low", "medium", "high"]) }, ["assetName", "description"]), true),
  t("plan_reference_image", "Plan Reference Image", "Create the reference-image brief before image generation.", s({ assetName: p(), profile: p(), description: p(), style: p(), view: p(), background: p(), seed: i() }, ["assetName", "description"]), true),
  t("register_reference_image", "Register Reference Image", "Register or copy a reference image into the work folder.", s({ workDir: p(), assetName: p(), imagePath: p(), source: e(["codex", "user", "unity", "manual"]), prompt: p(), copyIntoWorkDir: b() }, ["workDir", "assetName", "imagePath"])),
  t("validate_reference_image", "Validate Reference Image", "Validate local reference image readiness before TRELLIS2.", s({ imagePath: p(), expectedObject: p(), profile: p(), force: b() }, ["imagePath"]), true),
  t("run_asset_pipeline", "Run Asset Pipeline", "Run the foreground local image-to-3D pipeline.", pipelineSchema(["assetName", "referenceImagePath", "workDir"])),
  t("start_asset_pipeline_job", "Start Asset Pipeline Job", "Start a persistent monitorable job with events, logs, instructions and artifacts.", pipelineSchema(["assetName", "workDir"])),
  t("job_status", "Job Status", "Inspect a persistent job after restart and report state, warnings, artifacts and next actions.", s({ workDir: p(), jobId: p(), includeLogs: b() }, ["workDir"]), true),
  t("add_pipeline_instruction", "Add Pipeline Instruction", "Append a timestamped user/Codex/manual runtime instruction to a job.", s({ workDir: p(), jobId: p(), instruction: p(), author: e(["user", "codex", "manual"]) }, ["workDir", "instruction"])),
  t("cancel_pipeline_job", "Cancel Pipeline Job", "Cancel an active local pipeline process and persist cancelled state.", s({ workDir: p(), jobId: p() }, ["jobId"]), false, {}, true),
  t("adjust_generated_asset", "Adjust Generated Asset", "Correct GLB bounds, pivot, rotation, scale, axis remap and offset without rerunning TRELLIS2.", s({ inputMesh: p(), outputMesh: p(), rotateEuler: p(), scale: p(), offset: p(), targetBounds: p(), pivot: e(["bottom-center", "center", "origin", "custom", "keep"]), axisRemap: p(), customPivot: p(), tolerance: n(), report: p() }, ["inputMesh", "outputMesh"])),
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
    assetName: p(), profile: p(), referenceImagePath: p(), workDir: p(), targetWidth: n(), targetHeight: n(), targetDepth: n(),
    unityProject: p(), comfyServer: p(), workflow: e(["simple", "low-poly", "mesh-only-hq", "mesh-with-texturing", "mesh-with-texturing-hq"]),
    seed: i(), targetFaces: i(), textureSize: i(), maxViews: i(), dryRun: b(), skipGeneration: b(), forceReference: b(),
  }, required);
}
function respond(id, result) { process.stdout.write(`${JSON.stringify({ jsonrpc: "2.0", id, result })}\n`); }
function fail(id, code, message) { process.stdout.write(`${JSON.stringify({ jsonrpc: "2.0", id, error: { code, message } })}\n`); }
function result(data, text, meta = {}) { return { structuredContent: data, content: [{ type: "text", text }], _meta: meta }; }
function now() { return new Date().toISOString(); }
function safe(v) { return String(v || "asset").replace(/[^a-z0-9_.-]+/gi, "_").replace(/^_+|_+$/g, "") || "asset"; }
function readJson(file, fallback = null) { try { return JSON.parse(readFileSync(file, "utf8")); } catch { return fallback; } }
function writeJson(file, value) { mkdirSync(path.dirname(file), { recursive: true }); writeFileSync(file, JSON.stringify(value, null, 2), "utf8"); }
function appendJsonl(file, value) { mkdirSync(path.dirname(file), { recursive: true }); appendFileSync(file, `${JSON.stringify(value)}\n`, "utf8"); }
function loadProfiles() {
  const out = {};
  if (existsSync(profilesDir)) for (const file of readdirSync(profilesDir).filter((x) => x.endsWith(".json"))) out[path.basename(file, ".json")] = readJson(path.join(profilesDir, file), {});
  return out;
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
  }
  if (best) return { name: best.profileId, data: best.data, reason: `description-alias:${best.alias}` };
  return { name: "prop", data: all.prop || {}, reason: "fallback-prop" };
}
function availableProfileSummaries() {
  return Object.entries(loadProfiles()).map(([profileId, data]) => ({
    profileId,
    displayName: data.displayName || profileId,
    aliases: data.aliases || [profileId],
    targetBounds: data.targetBounds,
    faceBudget: data.faceBudget,
    textureSize: data.textureSize,
    pivotMode: data.pivotMode,
    unityCategory: data.unityCategory,
  }));
}
function bounds(args, profile) {
  const d = profile?.targetBounds || {};
  return { width: Number(args.targetWidth ?? d.x ?? 1), height: Number(args.targetHeight ?? d.y ?? 1), depth: Number(args.targetDepth ?? d.z ?? 1) };
}
function jobRoot(workDir) { return path.join(path.resolve(workDir), ".codex_asset_jobs"); }
function jobDir(workDir, jobId) { return path.join(jobRoot(workDir), jobId); }
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
function tryKillPid(pid) {
  const value = Number(pid);
  if (!Number.isFinite(value) || value <= 0) return { sent: false, error: "invalid pid" };
  try { process.kill(value); return { sent: true }; } catch (error) { return { sent: false, error: String(error?.message || error) }; }
}
function createJob(args, state = "planned") {
  const jobId = `${Date.now()}_${safe(args.assetName)}`;
  const dir = jobDir(args.workDir, jobId);
  ensureJobFiles(dir);
  const job = { jobId, assetName: args.assetName, profile: args.profile || "", state, status: state, createdAt: now(), updatedAt: now(), workDir: path.resolve(args.workDir), jobDir: dir, runWorkDir: path.join(dir, "work"), args };
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
function fileTail(file, max = 6000) { if (!existsSync(file)) return ""; const text = readFileSync(file, "utf8"); return text.slice(Math.max(0, text.length - max)); }
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
  const bnd = bounds(args, selected.data);
  const prompt = [
    `Create one ${selected.name} reference image for image-to-3D reconstruction.`,
    `Subject: ${args.description}`,
    args.style ? `Style: ${args.style}` : "Style: project-defined game asset style.",
    ...(selected.data.promptRules || []),
    "Camera: 3/4 slightly top-down unless profile or user says otherwise.",
    "Background: flat uniform plain background, no floor plane, no shadow.",
    "Do not draw text, dimension marks, rulers, labels, UI, or multiple objects.",
  ].join("\n");
  return result({ assetName: args.assetName, profile: selected.name, profileReason: selected.reason, displayName: selected.data.displayName || selected.name, referencePrompt: prompt, negativePromptRules: selected.data.negativePromptRules || [], targetBounds: bnd, faceBudget: selected.data.faceBudget || 9000, textureSize: selected.data.textureSize || 1024, pivotMode: selected.data.pivotMode || "bottom-center", unityCategory: selected.data.unityCategory || "props", generationDefaults: selected.data.generationDefaults || {}, importDefaults: selected.data.importDefaults || {}, validationRules: selected.data.validationRules || {}, availableProfiles: availableProfileSummaries(), nextActions: ["plan_reference_image", "register_reference_image", "validate_reference_image", "start_asset_pipeline_job"] }, `Planned ${args.assetName} with profile ${selected.name}.`);
}
function planReferenceImage(args) {
  const selected = profileFor(args.profile, args.description);
  const prompt = [
    `Reference image for ${args.assetName}.`,
    `Object: ${args.description}`,
    args.style ? `Style: ${args.style}` : "Style: coherent with project assets.",
    ...(selected.data.promptRules || []),
    `View: ${args.view || "3/4 top-down, entire object visible"}.`,
    `Background: ${args.background || "plain uniform matte background"}.`,
    "Lighting: even, no cast shadow, no text, no measurements, one object only.",
  ].join("\n");
  return result({ assetName: args.assetName, profile: selected.name, prompt, seed: args.seed ?? 2146628683, nextAction: "Create the image, save it locally, then call register_reference_image." }, `Reference image plan ready for ${args.assetName}.`);
}
function validateReferenceImageData(imagePath, expectedObject, force) {
  const script = path.join(pluginRoot, "scripts", "validate_reference_image.py");
  if (existsSync(script)) {
    const command = [script, "--image", imagePath, "--expected-object", expectedObject || "asset"];
    if (force) command.push("--force");
    const completed = spawnSync("python", command, { cwd: pluginRoot, encoding: "utf8", windowsHide: true });
    if (completed.stdout) {
      try {
        const parsed = JSON.parse(completed.stdout);
        parsed.validator = { command: ["python", ...command], exitCode: completed.status ?? 0, stderr: completed.stderr || "" };
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
  const bnd = bounds(args, selected.data);
  const command = [
    "python", path.join(pluginRoot, "scripts", "generate_asset.py"),
    "--asset-name", args.assetName,
    "--reference-image", args.referenceImagePath || path.join(job?.jobDir || args.workDir, "missing_reference.png"),
    "--work-dir", job?.runWorkDir || args.workDir,
    "--target-width", String(bnd.width),
    "--target-height", String(bnd.height),
    "--target-depth", String(bnd.depth),
    "--server", args.comfyServer || "http://127.0.0.1:8000",
    "--workflow", args.workflow || "simple",
    "--seed", String(args.seed ?? 2146628683),
    "--target-faces", String(args.targetFaces ?? selected.data.faceBudget ?? 9000),
    "--texture-size", String(args.textureSize ?? selected.data.textureSize ?? 1024),
    "--max-views", String(args.maxViews ?? 4),
  ];
  if (args.unityProject) command.push("--unity-project", args.unityProject);
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
  if (args.dryRun) return result({ command, dryRun: true, profile: profileFor(args.profile).name }, "Dry-run command planned; no process launched.");
  const out = await runProcess(command, { cwd: pluginRoot });
  return result({ command, exitCode: out.exitCode, stdout: out.stdout.slice(-10000), stderr: out.stderr.slice(-10000), workDir: path.resolve(args.workDir) }, out.exitCode === 0 ? `Pipeline completed for ${args.assetName}.` : `Pipeline failed for ${args.assetName}.`);
}
function startAssetPipelineJob(args) {
  const job = createJob(args, "queued");
  const command = buildPipelineCommand(args, job);
  let saved = updateJob(job, { command, profile: profileFor(args.profile).name });
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
  saved = updateJob(saved, { state: "generating", pid: child.pid, startedAt: now() });
  appendEvent(job.jobDir, "process_started", { pid: child.pid });
  activeJobs.set(job.jobId, { ...saved, child });
  child.stdout.on("data", (chunk) => { appendFileSync(stdoutPath, chunk, "utf8"); appendEvent(job.jobDir, "stdout", { bytes: chunk.length }); });
  child.stderr.on("data", (chunk) => { appendFileSync(stderrPath, chunk, "utf8"); appendEvent(job.jobDir, "stderr", { bytes: chunk.length }); });
  child.on("error", (error) => {
    const current = readJson(path.join(job.jobDir, "job.json"), saved);
    updateJob(current, { state: "failed", endedAt: now(), error: String(error) });
    appendEvent(job.jobDir, "process_error", { error: String(error) });
    activeJobs.delete(job.jobId);
  });
  child.on("close", (exitCode) => {
    const current = readJson(path.join(job.jobDir, "job.json"), saved);
    const artifacts = scanArtifacts(job.jobDir);
    writeJson(path.join(job.jobDir, "artifacts.json"), { artifacts });
    const hasUnity = artifacts.some((x) => x.path.includes("UnityReady") || x.path.endsWith("unity_import_manifest.json"));
    const state = exitCode === 0 ? (hasUnity ? "unity_ready" : "generated") : "failed";
    updateJob(current, { state, exitCode: exitCode ?? 1, endedAt: now() });
    appendEvent(job.jobDir, "process_closed", { exitCode, state, artifactCount: artifacts.length });
    activeJobs.delete(job.jobId);
  });
  return result({ jobId: job.jobId, pid: child.pid, state: "generating", command, jobDir: job.jobDir, stdoutPath, stderrPath }, `Started monitorable pipeline job ${job.jobId}.`);
}
function jobStatus(args) {
  const id = !args.jobId || args.jobId === "latest" ? latestJobId(args.workDir) : args.jobId;
  if (!id) return result({ workDir: path.resolve(args.workDir), found: false, jobsRoot: jobRoot(args.workDir) }, "No persistent job found.");
  const dir = jobDir(args.workDir, id);
  ensureJobFiles(dir);
  const job = readJson(path.join(dir, "job.json"), { jobId: id, state: "unknown", jobDir: dir });
  const artifacts = scanArtifacts(dir);
  writeJson(path.join(dir, "artifacts.json"), { artifacts });
  const warnings = [];
  const processState = { activeInThisSession: activeJobs.has(id), pid: job.pid || null, pidAlive: job.pid ? isPidAlive(job.pid) : false };
  if (job.state === "generated" && !artifacts.some((x) => x.kind === "mesh")) warnings.push("state says generated but no mesh artifact was found");
  if (job.state === "generating" && job.pid && !processState.activeInThisSession && processState.pidAlive) warnings.push("process is still running but MCP memory was restarted; cancellation can use persisted pid");
  if (job.state === "generating" && job.pid && !processState.pidAlive) warnings.push("job is marked generating but persisted pid is not running");
  const data = { job, process: processState, warnings, artifacts, nextActions: nextActions(job.state, artifacts), eventsPath: path.join(dir, "events.jsonl"), instructionsPath: path.join(dir, "instructions.jsonl"), stdoutPath: path.join(dir, "stdout.log"), stderrPath: path.join(dir, "stderr.log"), stdoutTail: args.includeLogs ? fileTail(path.join(dir, "stdout.log")) : undefined, stderrTail: args.includeLogs ? fileTail(path.join(dir, "stderr.log")) : undefined };
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
  const id = !args.jobId || args.jobId === "latest" ? latestJobId(args.workDir) : args.jobId;
  const dir = id ? jobDir(args.workDir, id) : jobRoot(args.workDir);
  mkdirSync(dir, { recursive: true });
  const entry = { at: now(), author: args.author || "user", instruction: args.instruction };
  appendJsonl(path.join(dir, "instructions.jsonl"), entry);
  appendEvent(dir, "instruction_added", entry);
  return result({ jobId: id || null, instructionsPath: path.join(dir, "instructions.jsonl"), entry }, `Instruction recorded: ${args.instruction}`);
}
function cancelPipelineJob(args) {
  const id = args.jobId === "latest" ? latestJobId(args.workDir || ".") : args.jobId;
  const active = activeJobs.get(id);
  const dir = args.workDir ? jobDir(args.workDir, id) : active?.jobDir;
  let killResult = { sent: false, source: "none" };
  if (active?.child) {
    active.child.kill();
    killResult = { sent: true, source: "active-child" };
  } else if (dir && existsSync(path.join(dir, "job.json"))) {
    const persisted = readJson(path.join(dir, "job.json"), {});
    if (persisted.pid && isPidAlive(persisted.pid)) killResult = { ...tryKillPid(persisted.pid), source: "persisted-pid" };
    else killResult = { sent: false, source: "persisted-pid", error: persisted.pid ? "pid not running" : "missing pid" };
  }
  if (dir && existsSync(dir)) {
    ensureJobFiles(dir);
    const job = readJson(path.join(dir, "job.json"), { jobId: id, jobDir: dir });
    updateJob(job, { state: "cancelled", endedAt: now(), cancel: killResult });
    appendEvent(dir, "cancelled", { by: "tool", kill: killResult });
  }
  activeJobs.delete(id);
  return result({ jobId: id, foundActive: !!active, state: "cancelled", kill: killResult }, `Cancelled job ${id}.`);
}
async function adjustGeneratedAsset(args) {
  const command = ["python", path.join(pluginRoot, "scripts", "normalize_asset_bounds.py"), "--input", args.inputMesh, "--output", args.outputMesh, "--rotate-euler", args.rotateEuler || "0,0,0", "--scale", args.scale || "1,1,1", "--offset", args.offset || "0,0,0", "--pivot", args.pivot || "bottom-center"];
  if (args.targetBounds) command.push("--target-bounds", args.targetBounds);
  if (args.axisRemap) command.push("--axis-remap", args.axisRemap);
  if (args.customPivot) command.push("--custom-pivot", args.customPivot);
  if (args.tolerance !== undefined) command.push("--tolerance", String(args.tolerance));
  if (args.report) command.push("--report", args.report);
  const out = await runProcess(command, { cwd: pluginRoot });
  return result({ command, exitCode: out.exitCode, stdout: out.stdout.slice(-10000), stderr: out.stderr.slice(-10000) }, out.exitCode === 0 ? "Asset adjustment complete." : "Asset adjustment failed.");
}
async function importAssetToUnity(args) {
  const mesh = path.resolve(args.meshPath);
  if (!existsSync(mesh)) throw new Error(`meshPath not found: ${mesh}`);
  const importDir = path.join(path.dirname(mesh), ".unity_import", safe(args.assetId || path.basename(mesh, path.extname(mesh))));
  mkdirSync(importDir, { recursive: true });
  const stagedMesh = path.join(importDir, path.basename(mesh));
  if (stagedMesh !== mesh) copyFileSync(mesh, stagedMesh);
  const command = ["python", path.join(pluginRoot, "scripts", "postprocess_generation.py"), "--batch-output-dir", importDir, "--unity-project", args.unityProject, "--unity-subdir", args.unitySubdir || "Assets/AIAssetPipeline/Generated/UnityReady", "--select", "newest", "--limit", "1", "--asset-id", args.assetId || path.basename(mesh, path.extname(mesh)), "--reference-image", args.referenceImagePath || "", "--workflow-label", "trellis2", "--generation-profile", "CodexAssetFactory", "--validation-profile", "CodexPostGeneration"];
  if (args.normalizationReport) command.push("--normalization-report", args.normalizationReport);
  if (args.characterAttachments) command.push("--character-attachments", args.characterAttachments);
  if (args.dryRun) command.push("--dry-run");
  const out = await runProcess(command, { cwd: pluginRoot });
  return result({ command, exitCode: out.exitCode, stdout: out.stdout.slice(-10000), stderr: out.stderr.slice(-10000), unityProject: args.unityProject }, out.exitCode === 0 ? "Unity import manifest/copy complete." : "Unity import failed.");
}
async function installUnityTemplate(args) {
  const script = path.join(pluginRoot, "scripts", "install_unity_template.ps1");
  const command = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script, "-UnityProjectRoot", args.unityProject];
  if (args.force) command.push("-Force");
  const out = await runProcess(command, { cwd: pluginRoot });
  return result({ command, exitCode: out.exitCode, stdout: out.stdout, stderr: out.stderr }, out.exitCode === 0 ? "Unity template installed." : "Unity template install failed.");
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
  const command = ["python", path.join(pluginRoot, "scripts", "character_attachment_manifest.py"), sub, ...extra];
  const out = await runProcess(command, { cwd: pluginRoot });
  return result({ command, exitCode: out.exitCode, stdout: out.stdout, stderr: out.stderr }, out.exitCode === 0 ? `Character attachment ${sub} OK.` : `Character attachment ${sub} failed.`);
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
    child.stdout?.on("data", (x) => { stdout += x.toString(); });
    child.stderr?.on("data", (x) => { stderr += x.toString(); });
    child.on("error", (error) => resolve({ exitCode: 127, stdout, stderr: stderr + String(error) }));
    child.on("close", (exitCode) => resolve({ exitCode: exitCode ?? 1, stdout, stderr }));
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
    return fail(id, -32000, error?.stack || String(error));
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





