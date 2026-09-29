; Instalador do Windows (Inno Setup 6). Gere antes o executável com PyInstaller.
; Uso: ISCC /DAppVersion=0.2.0 instalador\RemovedorVirus.iss

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppName "Removedor de Vírus Android"
#define AppExe "RemovedorVirus.exe"

[Setup]
AppId={{6F3C2A1E-8B7D-4E5F-9A2C-1D3E5F7A9B0C}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=jhoni1517
AppPublisherURL=https://github.com/jhoni1517/Removedor_Virus
DefaultDirName={autopf}\Removedor de Virus Android
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=RemovedorVirus-Setup-{#AppVersion}
SetupIconFile=..\assets\icone.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Instala sem pedir administrador (pasta do usuário); o usuário pode escolher "todos os usuários".
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Languages]
Name: "ptbr"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\RemovedorVirus\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Libera o adb.exe para que a desinstalação consiga apagar os arquivos.
Filename: "{app}\_internal\platform-tools\adb.exe"; Parameters: "kill-server"; Flags: runhidden skipifdoesntexist; RunOnceId: "EncerrarADB"

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Codigo: Integer;
  Adb: String;
begin
  { Numa atualização, encerra o ADB da versão anterior para liberar os arquivos. }
  Adb := ExpandConstant('{app}\_internal\platform-tools\adb.exe');
  if FileExists(Adb) then
    Exec(Adb, 'kill-server', '', SW_HIDE, ewWaitUntilTerminated, Codigo);
  Result := '';
end;
