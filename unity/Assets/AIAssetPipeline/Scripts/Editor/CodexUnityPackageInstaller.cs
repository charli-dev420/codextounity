using System;
using System.IO;
using System.Threading;
using UnityEditor;
using UnityEditor.PackageManager;
using UnityEditor.PackageManager.Requests;
using UnityEngine;

namespace AIAssetFactory.EditorTools
{
    public static class CodexUnityPackageInstaller
    {
        public static void InstallFromCommandLine()
        {
            var packageName = GetCommandLineValue("-codexUnityPackage");
            var reportPath = GetCommandLineValue("-codexUnityPackageReport");
            var timeoutSeconds = ParseInt(GetCommandLineValue("-codexUnityPackageTimeoutSeconds"), 300);
            if (string.IsNullOrWhiteSpace(packageName))
            {
                packageName = "com.unity.cloud.gltfast";
            }
            if (string.IsNullOrWhiteSpace(reportPath))
            {
                reportPath = Path.Combine(Application.dataPath, "../CodexUnityPackageInstallerReport.json");
            }

            var report = new PackageInstallReport
            {
                schema = "codex.unityPackageInstall.v1",
                packageName = packageName,
                startedAt = DateTime.UtcNow.ToString("o"),
            };

            try
            {
                AddRequest request = Client.Add(packageName);
                var deadline = DateTime.UtcNow.AddSeconds(Math.Max(5, timeoutSeconds));
                while (!request.IsCompleted && DateTime.UtcNow < deadline)
                {
                    Thread.Sleep(100);
                }

                if (!request.IsCompleted)
                {
                    report.errors = new[] { $"package install timed out after {timeoutSeconds} seconds" };
                }
                else if (request.Status == StatusCode.Success)
                {
                    report.valid = true;
                    report.installedPackageName = request.Result?.name ?? string.Empty;
                    report.installedPackageVersion = request.Result?.version ?? string.Empty;
                    AssetDatabase.Refresh();
                }
                else
                {
                    report.errors = new[] { request.Error?.message ?? "package install failed" };
                }
            }
            catch (Exception error)
            {
                report.errors = new[] { error.Message };
            }

            report.finishedAt = DateTime.UtcNow.ToString("o");
            WriteReport(reportPath, report);
            if (!report.valid)
            {
                foreach (var error in report.errors)
                {
                    Debug.LogError($"[AIAssetFactory] Unity package install failed: {error}");
                }
                EditorApplication.Exit(2);
                return;
            }

            Debug.Log($"[AIAssetFactory] Unity package installed: {report.installedPackageName} {report.installedPackageVersion}");
            EditorApplication.Exit(0);
        }

        private static void WriteReport(string path, PackageInstallReport report)
        {
            var parent = Path.GetDirectoryName(path);
            if (!string.IsNullOrWhiteSpace(parent))
            {
                Directory.CreateDirectory(parent);
            }
            File.WriteAllText(path, JsonUtility.ToJson(report, true));
        }

        private static string GetCommandLineValue(string name)
        {
            var args = Environment.GetCommandLineArgs();
            for (var i = 0; i < args.Length - 1; i++)
            {
                if (string.Equals(args[i], name, StringComparison.OrdinalIgnoreCase))
                {
                    return args[i + 1];
                }
            }
            return string.Empty;
        }

        private static int ParseInt(string value, int fallback)
        {
            return int.TryParse(value, out var parsed) ? parsed : fallback;
        }

        [Serializable]
        private class PackageInstallReport
        {
            public string schema = string.Empty;
            public bool valid;
            public string packageName = string.Empty;
            public string installedPackageName = string.Empty;
            public string installedPackageVersion = string.Empty;
            public string startedAt = string.Empty;
            public string finishedAt = string.Empty;
            public string[] errors = Array.Empty<string>();
        }
    }
}
