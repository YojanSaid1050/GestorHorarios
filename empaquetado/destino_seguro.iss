; Se valida antes de invocar Velopack: en modo silencioso puede reemplazar
; una carpeta ocupada y cerrar todos los procesos situados dentro de ella.
function AtributosRuta(Nombre: String): LongWord;
  external 'GetFileAttributesW@kernel32.dll stdcall setuponly';

function RutaNormalizada(Ruta: String): String;
begin
  Result := RemoveBackslash(ExpandFileName(Ruta));
end;

function DentroOIgual(Ruta, Base: String): Boolean;
begin
  Result := False;
  if Base = '' then Exit;
  Ruta := Lowercase(RutaNormalizada(Ruta));
  Base := Lowercase(RutaNormalizada(Base));
  Result := (Ruta = Base) or (Pos(AddBackslash(Base), AddBackslash(Ruta)) = 1);
end;

function RutaProtegida(Ruta: String): Boolean;
begin
  Result :=
    DentroOIgual(Ruta, ExpandConstant('{win}')) or
    DentroOIgual(Ruta, ExpandConstant('{commonpf32}')) or
    DentroOIgual(Ruta, ExpandConstant('{commonpf64}')) or
    DentroOIgual(Ruta, ExpandConstant('{commonappdata}')) or
    DentroOIgual(Ruta, ExpandConstant('{localappdata}\GestorHorarios-datos')) or
    DentroOIgual(ExpandConstant('{localappdata}\GestorHorarios-datos'), Ruta) or
    DentroOIgual(GetEnv('USERPROFILE'), Ruta) or
    DentroOIgual(ExpandConstant('{localappdata}'), Ruta) or
    DentroOIgual(ExpandConstant('{userappdata}'), Ruta) or
    DentroOIgual(ExpandConstant('{userdesktop}'), Ruta) or
    DentroOIgual(ExpandConstant('{userdocs}'), Ruta);
  if GetEnv('GESTOR_DATOS') <> '' then
    Result := Result or DentroOIgual(Ruta, GetEnv('GESTOR_DATOS')) or
      DentroOIgual(GetEnv('GESTOR_DATOS'), Ruta);
end;

function RutaConEnlaces(Ruta: String): Boolean;
var
  Atributos: LongWord;
  Padre: String;
begin
  Result := True;
  while Length(Ruta) > 3 do begin
    Atributos := AtributosRuta(Ruta);
    if (Atributos <> $FFFFFFFF) and ((Atributos and $400) <> 0) then Exit;
    Padre := RemoveBackslash(ExtractFileDir(Ruta));
    if Padre = Ruta then Exit;
    Ruta := Padre;
  end;
  Result := False;
end;

function ErrorRuta(Ruta: String): String;
var
  I: Integer;
begin
  Result := 'Elige una carpeta local dedicada a Gestor de Horarios.';
  if (Length(Ruta) < 4) or (Length(Ruta) > 200) then Exit;
  if (Ruta[2] <> ':') or (Ruta[3] <> '\') then Exit;
  if Pos(Uppercase(Ruta[1]), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ') = 0 then Exit;
  for I := 1 to Length(Ruta) do begin
    if Ord(Ruta[I]) < 32 then Exit;
    if Pos(Ruta[I], '"/<>|?*~') > 0 then Exit;
    if (I <> 2) and (Ruta[I] = ':') then Exit;
    if ((Ruta[I] = '.') or (Ruta[I] = ' ')) then begin
      if I = Length(Ruta) then Exit;
      if Ruta[I + 1] = '\' then Exit;
    end;
  end;
  Ruta := RutaNormalizada(Ruta);
  if Length(Ruta) < 4 then Exit;
  if RutaProtegida(Ruta) then begin
    Result := 'Esta carpeta está protegida o contiene datos personales. Elige una carpeta exclusiva para la aplicación.';
    Exit;
  end;
  if RutaConEnlaces(Ruta) then begin
    Result := 'La ruta contiene un enlace o una unión de carpetas. Elige una ubicación local directa.';
    Exit;
  end;
  Result := '';
end;

function EsInstalacionGestor(Ruta: String): Boolean;
var
  Manifiesto: AnsiString;
begin
  Result := False;
  if not FileExists(AddBackslash(Ruta) + 'Update.exe') then Exit;
  if not FileExists(AddBackslash(Ruta) + 'current\GestorHorarios.exe') then Exit;
  if not LoadStringFromFile(AddBackslash(Ruta) + 'current\sq.version', Manifiesto) then Exit;
  Result := Pos('<id>GestorHorarios</id>', String(Manifiesto)) > 0;
end;

function CarpetaVacia(Ruta: String): Boolean;
var
  Encontrado: TFindRec;
begin
  Result := False;
  if FileExists(Ruta) then Exit;
  if not DirExists(Ruta) then begin
    Result := True;
    Exit;
  end;
  if not FindFirst(AddBackslash(Ruta) + '*', Encontrado) then Exit;
  try
    repeat
      if (Encontrado.Name <> '.') and (Encontrado.Name <> '..') then Exit;
    until not FindNext(Encontrado);
  finally
    FindClose(Encontrado);
  end;
  Result := True;
end;

function ErrorDestino(Ruta, Anterior: String): String;
begin
  Result := ErrorRuta(Ruta);
  if Result <> '' then Exit;
  if (Anterior <> '') and
     (CompareText(RutaNormalizada(Ruta), RutaNormalizada(Anterior)) <> 0) then begin
    Result := 'Para actualizar, conserva la carpeta de la instalación existente.';
    Exit;
  end;
  if not CarpetaVacia(Ruta) and not EsInstalacionGestor(Ruta) then
    Result := 'La carpeta contiene archivos ajenos al Gestor. Selecciona una carpeta vacía; no se reemplazará su contenido.';
end;
