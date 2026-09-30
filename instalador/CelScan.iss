; Instalador do CelScan (Inno Setup 6). Gere antes o executável com PyInstaller.
; Uso: ISCC /DAppVersion=3.0.0b1 instalador\CelScan.iss

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppName "CelScan"
#define AppExe "CelScan.exe"
; AppId do antigo "Removedor de Vírus Android" (v0.2), que o CelScan substitui
#define AppIdAntigo "{6F3C2A1E-8B7D-4E5F-9A2C-1D3E5F7A9B0C}"

[Setup]
AppId={{9C1D5E77-2B4A-4C3F-8E61-5A0B7D3C2F14}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=jhoni1517
AppPublisherURL=https://github.com/jhoni1517/Removedor_Virus
DefaultDirName={autopf}\CelScan
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=CelScan-Setup-{#AppVersion}
SetupIconFile=..\assets\celscan.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Instala sem pedir administrador (pasta do usuário); dá para escolher "todos os usuários".
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
Source: "..\dist\CelScan\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

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
function DesinstaladorAntigo(Raiz: Integer): String;
var
  Valor: String;
begin
  Result := '';
  if RegQueryStringValue(Raiz, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#AppIdAntigo}_is1',
                         'UninstallString', Valor) then
    Result := RemoveQuotes(Valor);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Codigo: Integer;
  Adb, Antigo: String;
begin
  { Numa atualização, encerra o ADB da versão anterior para liberar os arquivos. }
  Adb := ExpandConstant('{app}\_internal\platform-tools\adb.exe');
  if FileExists(Adb) then
    Exec(Adb, 'kill-server', '', SW_HIDE, ewWaitUntilTerminated, Codigo);
  { Remove o antigo "Removedor de Vírus Android" (v0.2): o CelScan faz tudo o que ele fazia. }
  Antigo := DesinstaladorAntigo(HKCU);
  if Antigo = '' then
    Antigo := DesinstaladorAntigo(HKLM);
  if (Antigo <> '') and FileExists(Antigo) then
    Exec(Antigo, '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART', '', SW_HIDE, ewWaitUntilTerminated, Codigo);
  Result := '';
end;
