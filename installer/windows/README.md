# Windows Installer

This folder contains the Windows graphical installer source for Asset Factory. The executable is an experimental convenience entry point, not a supported, signed or guaranteed installer.

Build the experimental Windows executable from the repository root:

```powershell
.\installer\windows\build-installer.ps1
```

The generated file is:

```text
installer/windows/dist/AssetFactoryInstaller-win-x64/AssetFactoryInstaller.exe
```

Share that executable as an optional experimental download artifact for novice Windows users. Do not commit the generated `dist/`, `bin/` or `obj/` outputs.

The executable is a Windows Forms front end over the existing bootstrap engine. It runs the same dry-run, install and validate modes as `bootstrap/install.ps1`, shows component status, lists possible local writes, and keeps license/account-gated steps manual.

Novice path:

1. Double-click `AssetFactoryInstaller.exe`.
2. Run `Preflight and plan`.
3. Review `Local writes and local state`.
4. Review `Manual and source-review steps`.
5. Install only if the plan is clear and the experimental confirmation is acceptable.
6. Run `Validate setup`.

`Install missing allowed items` stays disabled until a successful preflight has been run with the current fields. Changing target, profile, fallback or paths requires a new preflight.

Windows SmartScreen may warn because this MVP executable is not code-signed. Treat that warning as expected for an unsigned experimental artifact. Review the source, build locally when possible, and do not bypass warnings unless you knowingly accept the risk.

Run the local non-destructive installer gate from the repository root:

```powershell
.\installer\windows\test-installer.ps1
```

The gate builds the executable, validates `--validate-launcher`, runs bootstrap dry-run and validate-only, and removes generated proof JSON.
