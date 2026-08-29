#!/usr/bin/env node

import { randomUUID } from "node:crypto";
import { readFileSync, renameSync, rmSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { mkdir } from "node:fs/promises";
import { pathToFileURL } from "node:url";

const [inputArg, outputArg, scriptsDirArg] = process.argv.slice(2);
if (!inputArg || !outputArg || !scriptsDirArg) {
  throw new Error("Usage: node deliver_structural_fallback.mjs <artifact.json> <report.html> <official-scripts-dir>");
}

const inputPath = resolve(inputArg);
const outputPath = resolve(outputArg);
const scriptsDir = resolve(scriptsDirArg);
const candidatePath = `${outputPath}.tmp-${process.pid}-${randomUUID()}.html`;

try {
  const [{ buildPortableArtifact }, { verifyPortableArtifactStructure }] = await Promise.all([
    import(pathToFileURL(resolve(scriptsDir, "build_portable_artifact.mjs")).href),
    import(pathToFileURL(resolve(scriptsDir, "verify_portable_artifact.mjs")).href),
  ]);
  const artifact = JSON.parse(readFileSync(inputPath, "utf8"));
  const html = buildPortableArtifact(artifact);
  await mkdir(dirname(outputPath), { recursive: true });
  writeFileSync(candidatePath, html, "utf8");
  const verification = verifyPortableArtifactStructure({
    artifactPath: inputPath,
    htmlPath: candidatePath,
  });
  if (!verification?.ok) {
    const error = new Error(verification?.error || "Structural verification failed.");
    error.verification = verification;
    throw error;
  }
  renameSync(candidatePath, outputPath);
  process.stdout.write(`${JSON.stringify({
    ok: true,
    output: outputPath,
    verificationStage: "structural_only",
    browserWarning: {
      code: "browser_timeout",
      message: "Chromium timed out; the official semantic fallback was structurally verified instead.",
    },
    verification,
  })}\n`);
} catch (error) {
  rmSync(candidatePath, { force: true });
  process.stderr.write(`${JSON.stringify({
    ok: false,
    error: error?.message || String(error),
    verification: error?.verification,
  })}\n`);
  process.exitCode = 1;
}
