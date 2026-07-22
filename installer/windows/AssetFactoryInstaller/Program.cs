using System.Diagnostics;
using System.Text;
using System.Text.Json;

namespace AssetFactoryInstaller;

internal static class Program
{
    [STAThread]
    private static int Main(string[] args)
    {
        if (args.Any(arg => string.Equals(arg, "--validate-launcher", StringComparison.OrdinalIgnoreCase)))
        {
            var root = ReadOption(args, "--plugin-root") ?? InstallerForm.LocatePluginRoot();
            return File.Exists(Path.Combine(root, "bootstrap", "install.ps1")) ? 0 : 2;
        }

        ApplicationConfiguration.Initialize();
        Application.Run(new InstallerForm());
        return 0;
    }

    private static string? ReadOption(string[] args, string optionName)
    {
        for (var i = 0; i < args.Length - 1; i++)
        {
            if (string.Equals(args[i], optionName, StringComparison.OrdinalIgnoreCase))
            {
                return args[i + 1];
            }
        }
        return null;
    }
}

internal sealed class InstallerForm : Form
{
    private readonly ComboBox targetBox = new();
    private readonly ComboBox profileBox = new();
    private readonly ComboBox fallbackBox = new();
    private readonly TextBox pluginRootBox = new();
    private readonly TextBox installRootBox = new();
    private readonly TextBox codexHomeBox = new();
    private readonly TextBox unityProjectBox = new();
    private readonly TextBox outputBox = new();
    private readonly Label statusLabel = new();
    private readonly Label summaryLabel = new();
    private readonly ListView componentsView = new();
    private readonly ListView localWritesView = new();
    private readonly ListView manualStepsView = new();
    private readonly Button preflightButton = new();
    private readonly Button installButton = new();
    private readonly Button validateButton = new();
    private readonly Button copyCommandButton = new();
    private readonly Button copyManualSourceButton = new();
    private readonly Button browsePluginButton = new();
    private readonly Button openDocsButton = new();

    private string lastMode = "dry-run";
    private string approvedPreflightFingerprint = "";
    private bool busy;

    public InstallerForm()
    {
        Text = "Asset Factory Installer";
        StartPosition = FormStartPosition.CenterScreen;
        MinimumSize = new Size(1060, 720);
        Size = new Size(1180, 780);

        BuildLayout();
        pluginRootBox.Text = LocatePluginRoot();
        targetBox.SelectedItem = "windows";
        profileBox.SelectedItem = "auto";
        fallbackBox.SelectedItem = "auto";
        installButton.Enabled = false;
        WireInputChangeHandlers();
        SetIdleStatus("Ready. Run Preflight and plan before install.");
    }

    private void BuildLayout()
    {
        var root = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            ColumnCount = 2,
            RowCount = 3,
            Padding = new Padding(16),
        };
        root.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 390));
        root.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        root.RowStyles.Add(new RowStyle(SizeType.Absolute, 80));
        root.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        root.RowStyles.Add(new RowStyle(SizeType.Absolute, 32));
        Controls.Add(root);

        var header = new Panel { Dock = DockStyle.Fill };
        var title = new Label
        {
            Text = "Asset Factory Installer",
            Dock = DockStyle.Top,
            Height = 32,
            Font = new Font(Font.FontFamily, 18, FontStyle.Bold),
        };
        var subtitle = new Label
        {
            Text = "Experimental prototype, broadly untested, with no guarantee. Run preflight, review local writes and manual steps, then install only if the plan is clear.",
            Dock = DockStyle.Top,
            Height = 38,
            ForeColor = Color.DimGray,
        };
        header.Controls.Add(subtitle);
        header.Controls.Add(title);
        root.Controls.Add(header, 0, 0);
        root.SetColumnSpan(header, 2);

        root.Controls.Add(BuildConfigurationPanel(), 0, 1);
        root.Controls.Add(BuildResultPanel(), 1, 1);

        statusLabel.Dock = DockStyle.Fill;
        statusLabel.TextAlign = ContentAlignment.MiddleLeft;
        root.Controls.Add(statusLabel, 0, 2);
        root.SetColumnSpan(statusLabel, 2);
    }

    private Control BuildConfigurationPanel()
    {
        var panel = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            ColumnCount = 1,
            RowCount = 14,
            Padding = new Padding(0, 0, 14, 0),
            AutoScroll = true,
        };
        for (var i = 0; i < 14; i++)
        {
            panel.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        }

        var warning = new Label
        {
            Text = "Experimental prototype. No stable support, no compatibility promise, no guarantee. Account, license and model-gated steps stay manual.",
            AutoSize = false,
            Height = 58,
            Dock = DockStyle.Top,
            Padding = new Padding(10),
            BackColor = Color.FromArgb(255, 248, 232),
            ForeColor = Color.FromArgb(120, 78, 0),
        };
        panel.Controls.Add(warning);

        ConfigureCombo(targetBox, "auto", "windows", "linux", "wsl", "docker");
        ConfigureCombo(profileBox, "auto", "cpu", "ada", "blackwell");
        ConfigureCombo(fallbackBox, "auto", "semi-auto", "manual");

        panel.Controls.Add(Labeled("Target", targetBox));
        panel.Controls.Add(Labeled("Profile", profileBox));
        panel.Controls.Add(Labeled("Fallback", fallbackBox));
        panel.Controls.Add(Labeled("Plugin root", pluginRootBox, browsePluginButton));
        panel.Controls.Add(Labeled("Install root", installRootBox));
        panel.Controls.Add(Labeled("Codex home", codexHomeBox));
        panel.Controls.Add(Labeled("Unity project", unityProjectBox));

        browsePluginButton.Text = "Browse";
        browsePluginButton.Click += (_, _) => BrowseForPluginRoot();

        preflightButton.Text = "1. Preflight and plan";
        preflightButton.Height = 42;
        preflightButton.Click += async (_, _) => await RunInstallerAsync("dry-run");
        panel.Controls.Add(preflightButton);

        installButton.Text = "2. Install missing allowed items";
        installButton.Height = 42;
        installButton.BackColor = Color.FromArgb(31, 102, 209);
        installButton.ForeColor = Color.White;
        installButton.Enabled = false;
        installButton.Click += async (_, _) => await RunInstallerAsync("install");
        panel.Controls.Add(installButton);

        validateButton.Text = "3. Validate setup";
        validateButton.Height = 42;
        validateButton.Click += async (_, _) => await RunInstallerAsync("validate-only");
        panel.Controls.Add(validateButton);

        copyCommandButton.Text = "Copy equivalent command";
        copyCommandButton.Height = 38;
        copyCommandButton.Click += (_, _) => Clipboard.SetText(BuildDisplayCommand(lastMode));
        panel.Controls.Add(copyCommandButton);

        copyManualSourceButton.Text = "Copy manual/source URL";
        copyManualSourceButton.Height = 38;
        copyManualSourceButton.Click += (_, _) => CopyManualSource();
        panel.Controls.Add(copyManualSourceButton);

        openDocsButton.Text = "Open installation docs";
        openDocsButton.Height = 38;
        openDocsButton.Click += (_, _) => OpenDocs();
        panel.Controls.Add(openDocsButton);

        return panel;
    }

    private Control BuildResultPanel()
    {
        var panel = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            ColumnCount = 1,
            RowCount = 8,
        };
        panel.RowStyles.Add(new RowStyle(SizeType.Absolute, 42));
        panel.RowStyles.Add(new RowStyle(SizeType.Absolute, 150));
        panel.RowStyles.Add(new RowStyle(SizeType.Absolute, 24));
        panel.RowStyles.Add(new RowStyle(SizeType.Absolute, 112));
        panel.RowStyles.Add(new RowStyle(SizeType.Absolute, 24));
        panel.RowStyles.Add(new RowStyle(SizeType.Absolute, 112));
        panel.RowStyles.Add(new RowStyle(SizeType.Absolute, 24));
        panel.RowStyles.Add(new RowStyle(SizeType.Percent, 100));

        summaryLabel.Dock = DockStyle.Fill;
        summaryLabel.TextAlign = ContentAlignment.MiddleLeft;
        summaryLabel.Font = new Font(Font.FontFamily, 10, FontStyle.Bold);
        panel.Controls.Add(summaryLabel);

        componentsView.Dock = DockStyle.Fill;
        componentsView.View = View.Details;
        componentsView.FullRowSelect = true;
        componentsView.GridLines = true;
        componentsView.Columns.Add("Component", 260);
        componentsView.Columns.Add("Status", 150);
        componentsView.Columns.Add("Source / note", 520);
        panel.Controls.Add(componentsView);

        panel.Controls.Add(SectionLabel("Local writes and local state"));

        localWritesView.Dock = DockStyle.Fill;
        localWritesView.View = View.Details;
        localWritesView.FullRowSelect = true;
        localWritesView.GridLines = true;
        localWritesView.Columns.Add("Area", 170);
        localWritesView.Columns.Add("Path / identifier", 310);
        localWritesView.Columns.Add("What may happen", 450);
        panel.Controls.Add(localWritesView);

        panel.Controls.Add(SectionLabel("Manual and source-review steps"));

        manualStepsView.Dock = DockStyle.Fill;
        manualStepsView.View = View.Details;
        manualStepsView.FullRowSelect = true;
        manualStepsView.GridLines = true;
        manualStepsView.Columns.Add("Component", 190);
        manualStepsView.Columns.Add("Status", 140);
        manualStepsView.Columns.Add("Manual action / source", 600);
        panel.Controls.Add(manualStepsView);

        panel.Controls.Add(SectionLabel("Raw output"));

        outputBox.Dock = DockStyle.Fill;
        outputBox.Multiline = true;
        outputBox.ScrollBars = ScrollBars.Both;
        outputBox.WordWrap = false;
        outputBox.Font = new Font("Consolas", 9);
        outputBox.Text = "Ready.";
        panel.Controls.Add(outputBox);

        return panel;
    }

    private static Label SectionLabel(string text)
    {
        return new Label
        {
            Text = text,
            Dock = DockStyle.Fill,
            TextAlign = ContentAlignment.BottomLeft,
            ForeColor = Color.DimGray,
            Font = new Font(SystemFonts.DefaultFont.FontFamily, 9, FontStyle.Bold),
        };
    }

    private static void ConfigureCombo(ComboBox combo, params string[] values)
    {
        combo.DropDownStyle = ComboBoxStyle.DropDownList;
        combo.Items.AddRange(values.Cast<object>().ToArray());
        combo.Width = 280;
    }

    private static Control Labeled(string label, Control control, Button? sideButton = null)
    {
        var wrapper = new TableLayoutPanel
        {
            Dock = DockStyle.Top,
            ColumnCount = sideButton is null ? 1 : 2,
            RowCount = 2,
            AutoSize = true,
            Margin = new Padding(0, 0, 0, 10),
        };
        wrapper.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        if (sideButton is not null)
        {
            wrapper.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 86));
        }
        var labelControl = new Label
        {
            Text = label,
            Dock = DockStyle.Fill,
            Height = 20,
            ForeColor = Color.DimGray,
        };
        wrapper.Controls.Add(labelControl, 0, 0);
        if (sideButton is not null)
        {
            wrapper.SetColumnSpan(labelControl, 2);
        }

        control.Dock = DockStyle.Top;
        control.Height = 28;
        wrapper.Controls.Add(control, 0, 1);
        if (sideButton is not null)
        {
            sideButton.Dock = DockStyle.Top;
            sideButton.Height = 28;
            wrapper.Controls.Add(sideButton, 1, 1);
        }
        return wrapper;
    }

    private void WireInputChangeHandlers()
    {
        targetBox.SelectedIndexChanged += (_, _) => ResetPreflightApproval();
        profileBox.SelectedIndexChanged += (_, _) => ResetPreflightApproval();
        fallbackBox.SelectedIndexChanged += (_, _) => ResetPreflightApproval();
        pluginRootBox.TextChanged += (_, _) => ResetPreflightApproval();
        installRootBox.TextChanged += (_, _) => ResetPreflightApproval();
        codexHomeBox.TextChanged += (_, _) => ResetPreflightApproval();
        unityProjectBox.TextChanged += (_, _) => ResetPreflightApproval();
    }

    private void ResetPreflightApproval()
    {
        if (!string.IsNullOrEmpty(approvedPreflightFingerprint))
        {
            approvedPreflightFingerprint = "";
            SetIdleStatus("Inputs changed. Run Preflight and plan again before installing.");
        }
        RefreshActionButtons();
    }

    private string CurrentInputFingerprint()
    {
        var values = new[]
        {
            Value(targetBox),
            Value(profileBox),
            Value(fallbackBox),
            pluginRootBox.Text.Trim(),
            installRootBox.Text.Trim(),
            codexHomeBox.Text.Trim(),
            unityProjectBox.Text.Trim(),
        };
        return string.Join("\n", values);
    }

    private bool IsInstallAllowed()
    {
        return !busy
            && !string.IsNullOrEmpty(approvedPreflightFingerprint)
            && string.Equals(approvedPreflightFingerprint, CurrentInputFingerprint(), StringComparison.Ordinal);
    }

    private void MarkPreflightApproved()
    {
        approvedPreflightFingerprint = CurrentInputFingerprint();
        RefreshActionButtons();
    }

    private void RefreshActionButtons()
    {
        if (busy) return;
        preflightButton.Enabled = true;
        validateButton.Enabled = true;
        copyCommandButton.Enabled = true;
        copyManualSourceButton.Enabled = true;
        browsePluginButton.Enabled = true;
        openDocsButton.Enabled = true;
        installButton.Enabled = IsInstallAllowed();
    }

    private async Task RunInstallerAsync(string mode)
    {
        lastMode = mode;
        var pluginRoot = pluginRootBox.Text.Trim();
        var installScript = Path.Combine(pluginRoot, "bootstrap", "install.ps1");
        if (!ValidateInputs(pluginRoot, installScript, out var validationError))
        {
            ShowFriendlyError(validationError, "");
            return;
        }
        if (mode == "install" && !IsInstallAllowed())
        {
            ShowFriendlyError("Run a successful Preflight and plan with the current fields before installing.", "");
            return;
        }
        if (mode == "install" && !ConfirmExperimentalInstall())
        {
            SetIdleStatus("Install cancelled.");
            return;
        }

        SetBusy(true, $"Running {ModeLabel(mode)}...");
        outputBox.Clear();
        AppendOutput(BuildDisplayCommand(mode));
        AppendOutput("");

        var stdout = new StringBuilder();
        var stderr = new StringBuilder();
        var exitCode = -1;
        var powerShell = ResolvePowerShell();
        if (string.IsNullOrWhiteSpace(powerShell))
        {
            SetBusy(false, "Ready.");
            ShowFriendlyError("PowerShell was not found on PATH.", "Install PowerShell 7 or ensure powershell.exe is available, then run Preflight again.");
            return;
        }

        try
        {
            var psi = new ProcessStartInfo
            {
                FileName = powerShell,
                WorkingDirectory = pluginRoot,
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true,
            };
            foreach (var arg in BuildPowerShellArguments(installScript, mode))
            {
                psi.ArgumentList.Add(arg);
            }

            using var process = new Process { StartInfo = psi, EnableRaisingEvents = true };
            process.OutputDataReceived += (_, e) =>
            {
                if (e.Data is null) return;
                stdout.AppendLine(e.Data);
                AppendOutput(e.Data);
            };
            process.ErrorDataReceived += (_, e) =>
            {
                if (e.Data is null) return;
                stderr.AppendLine(e.Data);
                AppendOutput(e.Data);
            };
            process.Start();
            process.BeginOutputReadLine();
            process.BeginErrorReadLine();
            await process.WaitForExitAsync();
            exitCode = process.ExitCode;
        }
        catch (Exception ex)
        {
            AppendOutput(ex.ToString());
            SetBusy(false, "Ready.");
            ShowFriendlyError("Installer failed to start.", BuildExceptionHint(ex));
            return;
        }
        finally
        {
            if (busy)
            {
                SetBusy(false, "Ready.");
            }
        }

        var parsed = RenderResult(stdout.ToString(), stderr.ToString(), exitCode, mode);
        if (mode == "dry-run" && parsed && exitCode == 0)
        {
            MarkPreflightApproved();
            SetIdleStatus("Preflight accepted. Install is now enabled until fields change.");
        }
    }

    private IEnumerable<string> BuildPowerShellArguments(string installScript, string mode)
    {
        yield return "-NoLogo";
        yield return "-NoProfile";
        yield return "-ExecutionPolicy";
        yield return "Bypass";
        yield return "-File";
        yield return installScript;
        if (mode == "dry-run") yield return "--dry-run";
        if (mode == "validate-only") yield return "--validate-only";
        yield return "--target";
        yield return Value(targetBox);
        yield return "--profile";
        yield return Value(profileBox);
        yield return "--fallback";
        yield return Value(fallbackBox);
        foreach (var item in OptionalArgs())
        {
            yield return item.Key;
            yield return item.Value;
        }
        yield return "--non-interactive";
        yield return "--json";
    }

    private Dictionary<string, string> OptionalArgs()
    {
        var args = new Dictionary<string, string>();
        AddIfPresent(args, "--install-root", installRootBox.Text);
        AddIfPresent(args, "--codex-home", codexHomeBox.Text);
        AddIfPresent(args, "--unity-project", unityProjectBox.Text);
        return args;
    }

    private static void AddIfPresent(Dictionary<string, string> args, string key, string value)
    {
        if (!string.IsNullOrWhiteSpace(value))
        {
            args[key] = value.Trim();
        }
    }

    private string BuildDisplayCommand(string mode)
    {
        var args = new List<string>();
        if (mode == "dry-run") args.Add("--dry-run");
        if (mode == "validate-only") args.Add("--validate-only");
        args.Add("--target " + Value(targetBox));
        args.Add("--profile " + Value(profileBox));
        args.Add("--fallback " + Value(fallbackBox));
        foreach (var item in OptionalArgs())
        {
            args.Add(item.Key + " \"" + item.Value + "\"");
        }
        args.Add("--non-interactive");
        args.Add("--json");
        return ".\\bootstrap\\install.ps1 " + string.Join(" ", args);
    }

    private bool RenderResult(string rawOutput, string rawError, int exitCode, string mode)
    {
        try
        {
            using var document = JsonDocument.Parse(rawOutput);
            var root = document.RootElement;
            var plan = root.GetProperty("plan");
            var summary = plan.GetProperty("summary");
            var state = plan.GetProperty("state").GetString() ?? "unknown";
            var target = plan.GetProperty("target").GetString() ?? "unknown";
            var profile = plan.GetProperty("profile").GetString() ?? "unknown";
            summaryLabel.Text =
                $"State: {state} | Target: {target} | Profile: {profile} | Present: {summary.GetProperty("present").GetInt32()} | Installable: {summary.GetProperty("installable").GetInt32()} | Manual: {summary.GetProperty("manualRequired").GetInt32()}";

            componentsView.Items.Clear();
            foreach (var step in plan.GetProperty("steps").EnumerateArray())
            {
                var name = JsonText(step, "name", JsonText(step, "id", "unknown"));
                var status = JsonText(step, "status", "unknown");
                var source = JsonText(step, "officialSource", "");
                var note = JsonText(step, "licenseNote", "");
                var item = new ListViewItem(name);
                item.SubItems.Add(status);
                item.SubItems.Add(string.IsNullOrWhiteSpace(note) ? source : source + " | " + note);
                item.BackColor = StatusBackColor(status);
                componentsView.Items.Add(item);
            }
            RenderLocalWrites(plan);
            RenderManualSteps(plan);

            if (exitCode == 0)
            {
                SetIdleStatus($"Done: {state}");
            }
            else
            {
                var hint = BuildFailureSummary(rawOutput, rawError, exitCode);
                summaryLabel.Text = hint;
                SetIdleStatus(hint);
                AppendOutput("");
                AppendOutput("Summary: " + hint);
            }
            return true;
        }
        catch (JsonException ex)
        {
            var hint = exitCode == 0
                ? "Command completed but returned output that is not valid installer JSON."
                : BuildFailureSummary(rawOutput, rawError, exitCode);
            summaryLabel.Text = hint;
            SetIdleStatus(hint);
            AppendOutput("");
            AppendOutput("Summary: " + hint);
            AppendOutput("JSON parse error: " + ex.Message);
            RenderNoStructuredData();
            return false;
        }
        catch (Exception ex)
        {
            var hint = "Could not render installer result. See raw output below.";
            summaryLabel.Text = hint;
            SetIdleStatus(hint);
            AppendOutput("");
            AppendOutput("Summary: " + hint);
            AppendOutput(ex.ToString());
            RenderNoStructuredData();
            return false;
        }
    }

    private void RenderLocalWrites(JsonElement plan)
    {
        localWritesView.Items.Clear();
        var environment = plan.GetProperty("environment");
        AddWriteRow("Install root", JsonText(environment, "installRoot", "<INSTALL_ROOT>"), "ComfyUI, virtualenv, models, workarounds and local runtime files when install runs.");
        AddWriteRow("Codex home", JsonText(environment, "codexHome", "<CODEX_HOME>"), "Plugin local/cache sync targets used by scripts/sync_plugin_install.ps1.");
        AddWriteRow("Plugin root", JsonText(environment, "pluginRoot", "<PLUGIN_ROOT>"), "Read as source; validation may create temporary proof JSON that must be removed before public push.");

        var unityProject = JsonText(environment, "unityProject", "");
        if (!string.IsNullOrWhiteSpace(unityProject))
        {
            AddWriteRow("Unity project", unityProject, "Unity template and MCP package files may be copied into the selected project.");
        }

        if (PlanMentionsDockerRuntime(plan))
        {
            AddWriteRow("Docker/runtime", JsonText(environment, "runtimeImage", "<RUNTIME_IMAGE>"), "Runtime image may be inspected, pulled or built if install mode is selected.");
        }
    }

    private bool PlanMentionsDockerRuntime(JsonElement plan)
    {
        foreach (var step in plan.GetProperty("steps").EnumerateArray())
        {
            var id = JsonText(step, "id", "");
            var status = JsonText(step, "status", "");
            if (id.Contains("docker", StringComparison.OrdinalIgnoreCase) ||
                string.Equals(status, "covered_by_runtime_image", StringComparison.OrdinalIgnoreCase))
            {
                return true;
            }
        }
        return false;
    }

    private void AddWriteRow(string area, string path, string note)
    {
        var item = new ListViewItem(area);
        item.SubItems.Add(path);
        item.SubItems.Add(note);
        localWritesView.Items.Add(item);
    }

    private void RenderManualSteps(JsonElement plan)
    {
        manualStepsView.Items.Clear();
        foreach (var step in plan.GetProperty("steps").EnumerateArray())
        {
            var status = JsonText(step, "status", "");
            if (status != "manual_required" && status != "source_review_required")
            {
                continue;
            }

            var name = JsonText(step, "name", JsonText(step, "id", "unknown"));
            var source = JsonText(step, "officialSource", "");
            var license = JsonText(step, "licenseNote", "");
            var action = JsonText(step, "manual", "");
            if (string.IsNullOrWhiteSpace(action))
            {
                action = JsonNestedText(step, "commands", "manual", "Review the official source and complete this step manually.");
            }
            var item = new ListViewItem(name);
            item.SubItems.Add(status);
            item.SubItems.Add($"{action} | {source} | {license}");
            item.Tag = source;
            item.BackColor = StatusBackColor(status);
            manualStepsView.Items.Add(item);
        }

        if (manualStepsView.Items.Count == 0)
        {
            var item = new ListViewItem("None");
            item.SubItems.Add("ready");
            item.SubItems.Add("No manual or source-review step is present in this plan.");
            manualStepsView.Items.Add(item);
        }
    }

    private void RenderNoStructuredData()
    {
        localWritesView.Items.Clear();
        manualStepsView.Items.Clear();
        componentsView.Items.Clear();
        AddWriteRow("Unknown", "See raw output", "The command did not return parseable installer JSON.");
        var item = new ListViewItem("Unknown");
        item.SubItems.Add("unknown");
        item.SubItems.Add("No structured manual/source-review data was available.");
        manualStepsView.Items.Add(item);
    }

    private static string JsonText(JsonElement element, string property, string fallback)
    {
        if (element.TryGetProperty(property, out var value) && value.ValueKind == JsonValueKind.String)
        {
            return value.GetString() ?? fallback;
        }
        return fallback;
    }

    private static string JsonNestedText(JsonElement element, string property, string childProperty, string fallback)
    {
        if (element.TryGetProperty(property, out var value)
            && value.ValueKind == JsonValueKind.Object
            && value.TryGetProperty(childProperty, out var child)
            && child.ValueKind == JsonValueKind.String)
        {
            return child.GetString() ?? fallback;
        }
        return fallback;
    }

    private static Color StatusBackColor(string status)
    {
        return status switch
        {
            "present" => Color.FromArgb(239, 250, 245),
            "installable" => Color.FromArgb(255, 248, 232),
            "manual_required" => Color.FromArgb(255, 248, 232),
            "source_review_required" => Color.FromArgb(255, 241, 241),
            "covered_by_runtime_image" => Color.FromArgb(236, 245, 255),
            _ => Color.White,
        };
    }

    private bool ValidateInputs(string pluginRoot, string installScript, out string error)
    {
        if (string.IsNullOrWhiteSpace(pluginRoot) || !Directory.Exists(pluginRoot))
        {
            error = "Selected plugin root does not exist.";
            return false;
        }
        if (!File.Exists(installScript))
        {
            error = "Cannot find bootstrap\\install.ps1 under the selected plugin root.";
            return false;
        }

        var unityProject = unityProjectBox.Text.Trim();
        if (!string.IsNullOrWhiteSpace(unityProject))
        {
            if (!Directory.Exists(unityProject))
            {
                error = "Unity project path does not exist.";
                return false;
            }
            if (!Directory.Exists(Path.Combine(unityProject, "Assets")))
            {
                error = "Unity project path is invalid: it must contain an Assets folder.";
                return false;
            }
        }

        error = "";
        return true;
    }

    private bool ConfirmExperimentalInstall()
    {
        using var dialog = new Form
        {
            Text = "Confirm experimental install",
            StartPosition = FormStartPosition.CenterParent,
            FormBorderStyle = FormBorderStyle.FixedDialog,
            MinimizeBox = false,
            MaximizeBox = false,
            ClientSize = new Size(560, 240),
        };

        var layout = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            ColumnCount = 1,
            RowCount = 4,
            Padding = new Padding(16),
        };
        layout.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 44));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 44));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 46));
        dialog.Controls.Add(layout);

        layout.Controls.Add(new Label
        {
            Dock = DockStyle.Fill,
            Text = "This installer is an experimental prototype. It may run installers, clone repositories, create local folders, sync Codex plugin files and write into a Unity project if one is selected. It is broadly untested and has no guarantee of any kind.",
            AutoSize = false,
        });

        var check = new CheckBox
        {
            Text = "I understand this is experimental and has no guarantee.",
            Dock = DockStyle.Fill,
        };
        layout.Controls.Add(check);

        var commandLabel = new TextBox
        {
            Dock = DockStyle.Fill,
            ReadOnly = true,
            Text = BuildDisplayCommand("install"),
        };
        layout.Controls.Add(commandLabel);

        var buttons = new FlowLayoutPanel
        {
            Dock = DockStyle.Fill,
            FlowDirection = FlowDirection.RightToLeft,
        };
        var install = new Button { Text = "Install", DialogResult = DialogResult.OK, Enabled = false, Width = 110 };
        var cancel = new Button { Text = "Cancel", DialogResult = DialogResult.Cancel, Width = 110 };
        check.CheckedChanged += (_, _) => install.Enabled = check.Checked;
        buttons.Controls.Add(install);
        buttons.Controls.Add(cancel);
        layout.Controls.Add(buttons);

        dialog.AcceptButton = install;
        dialog.CancelButton = cancel;
        return dialog.ShowDialog(this) == DialogResult.OK;
    }

    private void ShowFriendlyError(string summary, string detail)
    {
        summaryLabel.Text = summary;
        SetIdleStatus(summary);
        AppendOutput("");
        AppendOutput("ERROR: " + summary);
        if (!string.IsNullOrWhiteSpace(detail))
        {
            AppendOutput(detail);
        }
        MessageBox.Show(this, string.IsNullOrWhiteSpace(detail) ? summary : summary + Environment.NewLine + Environment.NewLine + detail, "Asset Factory Installer", MessageBoxButtons.OK, MessageBoxIcon.Error);
    }

    private static string BuildExceptionHint(Exception ex)
    {
        if (ex is UnauthorizedAccessException)
        {
            return "Permission was denied. Try a user-writable install root and avoid protected folders such as Program Files.";
        }
        if (ex is FileNotFoundException or DirectoryNotFoundException)
        {
            return "A required executable or folder could not be found. Check the plugin root and PowerShell installation.";
        }
        return ex.Message;
    }

    private static string BuildFailureSummary(string stdout, string stderr, int exitCode)
    {
        var text = (stdout + Environment.NewLine + stderr).Trim();
        if (text.Contains("UnauthorizedAccessException", StringComparison.OrdinalIgnoreCase) ||
            text.Contains("Access is denied", StringComparison.OrdinalIgnoreCase) ||
            text.Contains("permission", StringComparison.OrdinalIgnoreCase))
        {
            return "Permission denied. Use a user-writable install root and avoid protected folders.";
        }
        if (text.Contains("Unity project path missing or invalid", StringComparison.OrdinalIgnoreCase) ||
            text.Contains("must contain an Assets folder", StringComparison.OrdinalIgnoreCase))
        {
            return "Unity project path is invalid. Select a Unity project root that contains an Assets folder.";
        }
        if (text.Contains("Unknown installer argument", StringComparison.OrdinalIgnoreCase))
        {
            return "Installer arguments are invalid. Copy the equivalent command and review it.";
        }
        if (text.Contains("Cannot find path", StringComparison.OrdinalIgnoreCase) ||
            text.Contains("Could not find", StringComparison.OrdinalIgnoreCase) ||
            text.Contains("not recognized", StringComparison.OrdinalIgnoreCase))
        {
            return "A required command or path was not found. Review prerequisites and selected folders.";
        }
        return $"Command failed with exit code {exitCode}. Review raw output below.";
    }

    private void BrowseForPluginRoot()
    {
        using var dialog = new FolderBrowserDialog
        {
            Description = "Select the repository root containing bootstrap\\install.ps1",
            SelectedPath = Directory.Exists(pluginRootBox.Text) ? pluginRootBox.Text : Environment.CurrentDirectory,
        };
        if (dialog.ShowDialog(this) == DialogResult.OK)
        {
            pluginRootBox.Text = dialog.SelectedPath;
        }
    }

    private void CopyManualSource()
    {
        var values = new List<string>();
        if (manualStepsView.SelectedItems.Count > 0)
        {
            foreach (ListViewItem selected in manualStepsView.SelectedItems)
            {
                if (selected.Tag is string source && !string.IsNullOrWhiteSpace(source))
                {
                    values.Add(source);
                }
            }
        }
        else
        {
            foreach (ListViewItem item in manualStepsView.Items)
            {
                if (item.Tag is string source && !string.IsNullOrWhiteSpace(source))
                {
                    values.Add(source);
                }
            }
        }

        values = values.Distinct(StringComparer.OrdinalIgnoreCase).ToList();
        if (values.Count == 0)
        {
            MessageBox.Show(this, "No manual or source-review URL is available yet. Run Preflight and plan first.", "Nothing to copy", MessageBoxButtons.OK, MessageBoxIcon.Information);
            return;
        }
        Clipboard.SetText(string.Join(Environment.NewLine, values));
    }

    private void OpenDocs()
    {
        var path = Path.Combine(pluginRootBox.Text.Trim(), "docs", "en", "INSTALL.md");
        if (!File.Exists(path))
        {
            MessageBox.Show(this, "Installation docs were not found under docs\\en\\INSTALL.md.", "Docs missing", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }
        Process.Start(new ProcessStartInfo { FileName = path, UseShellExecute = true });
    }

    private void SetBusy(bool busy, string text)
    {
        this.busy = busy;
        foreach (var button in new[] { preflightButton, validateButton, copyCommandButton, copyManualSourceButton, browsePluginButton, openDocsButton })
        {
            button.Enabled = !busy;
        }
        installButton.Enabled = !busy && IsInstallAllowed();
        statusLabel.Text = text;
        Cursor = busy ? Cursors.WaitCursor : Cursors.Default;
    }

    private void SetIdleStatus(string text)
    {
        statusLabel.Text = text;
        summaryLabel.Text = text;
    }

    private void AppendOutput(string line)
    {
        if (outputBox.InvokeRequired)
        {
            outputBox.BeginInvoke(new Action(() => AppendOutput(line)));
            return;
        }
        outputBox.AppendText(line + Environment.NewLine);
    }

    private static string Value(ComboBox combo)
    {
        return (combo.SelectedItem as string) ?? combo.Text.Trim();
    }

    private static string ModeLabel(string mode)
    {
        return mode switch
        {
            "install" => "install",
            "validate-only" => "validation",
            _ => "preflight",
        };
    }

    internal static string LocatePluginRoot()
    {
        var env = Environment.GetEnvironmentVariable("ASSET_FACTORY_PLUGIN_ROOT");
        if (IsPluginRoot(env)) return Path.GetFullPath(env!);

        foreach (var start in new[] { AppContext.BaseDirectory, Environment.CurrentDirectory })
        {
            var current = new DirectoryInfo(start);
            for (var i = 0; current is not null && i < 8; i++, current = current.Parent)
            {
                if (IsPluginRoot(current.FullName)) return current.FullName;
            }
        }
        return Environment.CurrentDirectory;
    }

    private static bool IsPluginRoot(string? path)
    {
        return !string.IsNullOrWhiteSpace(path) && File.Exists(Path.Combine(path, "bootstrap", "install.ps1"));
    }

    private static string? ResolvePowerShell()
    {
        foreach (var candidate in new[] { "pwsh.exe", "powershell.exe" })
        {
            var found = FindOnPath(candidate);
            if (found is not null) return found;
        }
        return null;
    }

    private static string? FindOnPath(string fileName)
    {
        var path = Environment.GetEnvironmentVariable("PATH") ?? "";
        foreach (var entry in path.Split(Path.PathSeparator, StringSplitOptions.RemoveEmptyEntries))
        {
            try
            {
                var candidate = Path.Combine(entry.Trim(), fileName);
                if (File.Exists(candidate)) return candidate;
            }
            catch
            {
                // Ignore malformed PATH entries.
            }
        }
        return null;
    }
}
