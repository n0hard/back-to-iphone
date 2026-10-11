; Инсталлятор «Возврат» (Inno Setup 6). Сборка: build.bat в корне проекта.

#define AppName "Возврат"
#define AppVersion "1.0.0"
#define AppExe "Vozvrat.exe"

[Setup]
AppId={{6E0B3C4A-9B1E-4E7B-9A51-3D2F7C1A8E21}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Личное использование
DefaultDirName={localappdata}\Programs\Vozvrat
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist
OutputBaseFilename=VozvratSetup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Languages]
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Ярлыки:"

[Files]
Source: "..\build\dist\Vozvrat\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Удалить {#AppName}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "ms-windows-store://pdp/?ProductId=9NP83LWLPZ9K"; Description: "Установить драйвер Apple Devices из Microsoft Store (нужен, чтобы видеть iPhone)"; Flags: postinstall shellexec skipifsilent; Check: not AppleDriverInstalled
Filename: "{app}\{#AppExe}"; Description: "Запустить {#AppName}"; Flags: postinstall nowait skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
var
  DriverChecked, DriverFound: Boolean;

function AppleDriverInstalled: Boolean;
var
  Code: Integer;
begin
  if not DriverChecked then
  begin
    DriverChecked := True;
    { iTunes / Apple Mobile Device Support ставят службу; Apple Devices — пакет из Microsoft Store }
    DriverFound := RegKeyExists(HKLM, 'SYSTEM\CurrentControlSet\Services\Apple Mobile Device Service')
      or RegKeyExists(HKLM, 'SYSTEM\CurrentControlSet\Services\AppleMobileDeviceService');
    if not DriverFound then
      DriverFound := Exec('powershell.exe',
        '-NoProfile -NonInteractive -Command "if (Get-AppxPackage -Name AppleInc.AppleDevices) { exit 0 } else { exit 1 }"',
        '', SW_HIDE, ewWaitUntilTerminated, Code) and (Code = 0);
  end;
  Result := DriverFound;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if (CurPageID = wpReady) and not AppleDriverInstalled then
    MsgBox('Не найден драйвер Apple для работы с iPhone по USB.' + #13#10 + #13#10 +
      'После установки «Возврат» предложит открыть Microsoft Store, чтобы поставить бесплатное приложение Apple Devices ' +
      '(или установите iTunes с сайта Apple).', mbInformation, MB_OK);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usPostUninstall) and
     (SuppressibleMsgBox('Удалить также вход в Apple ID и сохранённые IPA?', mbConfirmation, MB_YESNO, IDNO) = IDYES) then
  begin
    { сессия ipatool «Возврата» лежит внутри vozvrat; общий ~/.ipatool принадлежит другим программам }
    DelTree(ExpandConstant('{userappdata}\vozvrat'), True, True, True);
  end;
end;
