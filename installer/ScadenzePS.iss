[Setup]
AppName=Scadenze PS
AppVersion=1.1.0
AppPublisher=Azienda
AppPublisherURL=
DefaultDirName={autopf}\Scadenze-PS
DefaultGroupName=Scadenze PS
UninstallDisplayIcon={app}\ScadenzePS.exe
OutputDir=..\dist
OutputBaseFilename=Scadenze-PS-Setup
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
SetupIconFile=
WizardStyle=modern
DisableProgramGroupPage=yes

[Languages]
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"

[Files]
Source: "..\dist\ScadenzePS\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autodesktop}\Scadenze PS"; Filename: "{app}\ScadenzePS.exe"; WorkingDir: "{app}"
Name: "{group}\Scadenze PS"; Filename: "{app}\ScadenzePS.exe"; WorkingDir: "{app}"
Name: "{group}\Disinstalla Scadenze PS"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\ScadenzePS.exe"; Description: "Avvia Scadenze PS"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\data"
Type: filesandordirs; Name: "{app}\config"
