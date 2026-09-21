#if VER < EncodeVer(6, 6, 0)
  #error Se requiere Inno Setup 6.6 o posterior para el estilo Windows 11.
#endif
; Asistente por usuario. Velopack conserva la instalación, actualización y desinstalación.
#ifndef VersionApp
  #error VersionApp debe proporcionarse desde construir.py
#endif
#ifndef InstaladorBase
  #error InstaladorBase debe indicar el Setup original de Velopack
#endif

[Setup]
AppId=GestorHorarios.Asistente
AppName=Gestor de Horarios
AppVersion={#VersionApp}
AppPublisher=xYojanSaidx
DefaultDirName={localappdata}\GestorHorarios
DisableDirPage=no
DisableProgramGroupPage=yes
DisableWelcomePage=no
PrivilegesRequired=lowest
WizardStyle=modern dynamic windows11
WizardSizePercent=110
SetupIconFile=icono.ico
WizardImageFile=arte\bienvenida.png
WizardSmallImageFile=arte\calendario.png
MinVersion=10.0.17763
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CreateAppDir=yes
UsePreviousAppDir=no
Uninstallable=no
CreateUninstallRegKey=no
OutputDir=..\dist\instalador
OutputBaseFilename=GestorHorarios-Instalar-{#VersionApp}
Compression=lzma2
SolidCompression=yes
SetupLogging=yes
CloseApplications=no


[Languages]
Name: spanish; MessagesFile: compiler:Languages\Spanish.isl

[Messages]
WelcomeLabel1=Tu equipo, mejor organizado.
WelcomeLabel2=Instala Gestor de Horarios para preparar turnos, revisar solicitudes y compartir la programación.%n%nEl asistente te guiará paso a paso. Si ya usas la aplicación, se conservarán tus datos de trabajo.
SelectDirLabel3=Elige dónde instalar la aplicación. Los horarios se guardan por separado en tu perfil de Windows.
ReadyLabel1=Todo listo para instalar
FinishedHeadingLabel=Tu próximo horario empieza aquí
FinishedLabel=Gestor de Horarios está instalado. Puedes abrirlo ahora y continuar con la programación de tu equipo.

[Tasks]
Name: desktopicon; Description: Crear un acceso directo en el escritorio; GroupDescription: Accesos directos:; Flags: unchecked

[Files]
Source: "{#InstaladorBase}"; DestName: MotorInstalacion.exe; Flags: dontcopy

[Icons]
Name: "{userdesktop}\Gestor de Horarios"; Filename: "{app}\current\GestorHorarios.exe"; WorkingDir: "{app}\current"; Tasks: desktopicon

[Run]
Filename: "{app}\current\GestorHorarios.exe"; Description: Abrir Gestor de Horarios; Flags: nowait postinstall skipifsilent

[Code]
var
  CarpetaAnterior: String;
  Progreso: TOutputMarqueeProgressWizardPage;
  Instalado: Boolean;

#include "destino_seguro.iss"

procedure InitializeWizard;
var
  Detectada: String;
begin
  Instalado := False;
  CarpetaAnterior := '';
  if RegQueryStringValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\GestorHorarios', 'InstallLocation', Detectada) then begin
    if (ErrorRuta(Detectada) = '') and EsInstalacionGestor(Detectada) then
      CarpetaAnterior := RutaNormalizada(Detectada)
    else
      Log('Se ignora una ruta registrada que no es una instalación válida y segura del Gestor.');
  end;
  if CarpetaAnterior <> '' then begin
    WizardForm.DirEdit.Text := CarpetaAnterior;
    WizardForm.DirEdit.Enabled := False;
    WizardForm.DirBrowseButton.Enabled := False;
    WizardForm.SelectDirLabel.Caption := 'Se actualizará la instalación existente. Tus datos y cuentas se conservan.';
  end;
  Progreso := CreateOutputMarqueeProgressPage('Instalando Gestor de Horarios', 'Preparando la aplicación y sus componentes. Este paso puede tardar unos minutos.');
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Error: String;
begin
  Result := True;
  if CurPageID = wpSelectDir then begin
    Error := ErrorDestino(WizardDirValue, CarpetaAnterior);
    if Error <> '' then begin
      if WizardSilent then Log(Error) else MsgBox(Error, mbError, MB_OK);
      Result := False;
    end;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Codigo: Integer;
  Destino: String;
begin
  Destino := WizardDirValue;
  Result := ErrorDestino(Destino, CarpetaAnterior);
  if Result <> '' then Exit;
  Destino := RutaNormalizada(Destino);
  if CompareText(Destino, RutaNormalizada(ExpandConstant('{app}'))) <> 0 then begin
    Result := 'La carpeta elegida no coincide con la carpeta del asistente. Se ha cancelado la instalación.';
    Exit;
  end;
  if Instalado then Exit;
  ForceDirectories(ExpandConstant('{localappdata}\GestorHorarios-datos'));
  Progreso.Show;
  Progreso.Animate;
  try
    Log('Destino validado para Velopack: ' + Destino);
    ExtractTemporaryFile('MotorInstalacion.exe');
    Progreso.SetText('Instalando la aplicación', 'Se comprobará Microsoft Edge WebView2. Si falta, su descarga requiere conexión a Internet.');
    if not Exec(ExpandConstant('{tmp}\MotorInstalacion.exe'), '--silent --installto "' + Destino + '" --log "' + ExpandConstant('{localappdata}\GestorHorarios-datos\instalacion.log') + '"', '', SW_HIDE, ewWaitUntilTerminated, Codigo) then
      Result := 'No se pudo iniciar la instalación. Revisa el espacio disponible y vuelve a intentarlo.'
    else if Codigo <> 0 then
      Result := 'La instalación no terminó (código ' + IntToStr(Codigo) + '). Registro: ' + ExpandConstant('{localappdata}\GestorHorarios-datos\instalacion.log')
    else if not FileExists(AddBackslash(Destino) + 'current\GestorHorarios.exe') then
      Result := 'No se encontró la aplicación instalada. Revisa el registro de instalación.'
    else Instalado := True;
  finally
    Progreso.Hide;
  end;
end;
