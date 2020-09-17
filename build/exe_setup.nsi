; Script for NullSoft Scriptable Install System, producing an executable
; installer for NightFall.
;
; Expected command-line parameters:
; /DVERSION=<program version>
; /DSUFFIX64=<"_x64" for 64-bit installer>
;
; @created   18.10.2012
; @modified  17.09.2020

Unicode True

!define PRODUCT_NAME "NightFall"
!define PRODUCT_PUBLISHER "Erki Suurjaak"
!define PRODUCT_WEB_SITE "https://suurjaak.github.io/NightFall"
!define BASENAME "nightfall"
!define PROGEXE "${BASENAME}.exe"
; VERSION and SUFFIX64 *should* come from command-line parameter
!define /ifndef VERSION "2.0"
!define /ifndef SUFFIX64 ""

!define PRODUCT_DIR_REGKEY "Software\Microsoft\Windows\CurrentVersion\App Paths\${PROGEXE}"
!define PRODUCT_UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}"

!define UNINSTALL_FILENAME "uninstall.exe"
; suggested name of directory to install (under $PROGRAMFILES or $LOCALAPPDATA)
!define MULTIUSER_INSTALLMODE_INSTDIR "${PRODUCT_NAME}"
; registry key for INSTALL info, placed under [HKLM|HKCU]\Software  (can be ${APP_NAME} or some {GUID})
!define MULTIUSER_INSTALLMODE_INSTALL_REGISTRY_KEY "${PRODUCT_NAME}"
; registry key for UNINSTALL info, placed under [HKLM|HKCU]\Software\Microsoft\Windows\CurrentVersion\Uninstall  (can be ${APP_NAME} or some {GUID})
!define MULTIUSER_INSTALLMODE_UNINSTALL_REGISTRY_KEY "${PRODUCT_NAME}"
!define MULTIUSER_INSTALLMODE_DEFAULT_REGISTRY_VALUENAME "UninstallString"
!define MULTIUSER_INSTALLMODE_INSTDIR_REGISTRY_VALUENAME "InstallLocation"
; allow requesting for elevation... if false, radiobutton will be disabled and user will have to restart installer with elevated permissions
!define MULTIUSER_INSTALLMODE_ALLOW_ELEVATION
; only available if MULTIUSER_INSTALLMODE_ALLOW_ELEVATION
!define MULTIUSER_INSTALLMODE_DEFAULT_ALLUSERS
!if "${SUFFIX64}" == "_x64"
  !define MULTIUSER_INSTALLMODE_64_BIT 1
!endif
!define LANG_ENGLISH 1033


!include NsisMultiUser.nsh
!include NsisMultiUserLang.nsh
!include MUI.nsh
!include nsProcess.nsh
!include RefreshSysTray.nsh
!include x64.nsh

!define MUI_TEXT_WELCOME_INFO_TEXT "This wizard will guide you through the installation of $(^NameDA).$\r$\n$\r$\n$_CLICK"

; MUI Settings
!define MUI_ABORTWARNING
!define MUI_ICON "${BASENAME}.ico"
!define MUI_UNICON "${NSISDIR}\Contrib\Graphics\Icons\modern-uninstall.ico"

; Welcome page
!insertmacro MUI_PAGE_WELCOME
; All users / current only
!insertmacro MULTIUSER_PAGE_INSTALLMODE
; Directory page
!insertmacro MUI_PAGE_DIRECTORY
; Instfiles page
!insertmacro MUI_PAGE_INSTFILES
; Finish page
!define MUI_PAGE_CUSTOMFUNCTION_PRE Startup_Pre
!define MUI_PAGE_CUSTOMFUNCTION_SHOW Startup_Show
!define MUI_PAGE_CUSTOMFUNCTION_LEAVE Startup_Leave
!define MUI_FINISHPAGE_RUN "$INSTDIR\${PROGEXE}"
!define MUI_FINISHPAGE_SHOWREADME "$INSTDIR\README.txt"
!define MUI_FINISHPAGE_SHOWREADME_NOTCHECKED
!insertmacro MUI_PAGE_FINISH

; Uninstaller pages
!insertmacro MULTIUSER_UNPAGE_INSTALLMODE
!insertmacro MUI_UNPAGE_INSTFILES

; Language files
!insertmacro MUI_LANGUAGE "English"


Name "${PRODUCT_NAME} ${VERSION}"
OutFile "${BASENAME}_${VERSION}${SUFFIX64}_setup.exe"
ShowInstDetails show
ShowUnInstDetails show


Function .OnInit
  !insertmacro MULTIUSER_INIT
FunctionEnd

Function Startup_Pre
  ; Edit iospecial.ini at runtime before finish page appears, add startup checkbox
  WriteINIStr "$PLUGINSDIR\iospecial.ini" "Settings" "NumFields" "6"
  WriteINIStr "$PLUGINSDIR\iospecial.ini" "Field 6" "Type" "CheckBox"
  WriteINIStr "$PLUGINSDIR\iospecial.ini" "Field 6" "Text" "Run &at startup"
  WriteINIStr "$PLUGINSDIR\iospecial.ini" "Field 6" "Left" "120"
  WriteINIStr "$PLUGINSDIR\iospecial.ini" "Field 6" "Right" "315"
  WriteINIStr "$PLUGINSDIR\iospecial.ini" "Field 6" "Top" "130"
  WriteINIStr "$PLUGINSDIR\iospecial.ini" "Field 6" "Bottom" "140"
  WriteINIStr "$PLUGINSDIR\iospecial.ini" "Field 6" "State" "1"
FunctionEnd

Function Startup_Show
  ReadINIStr $0 "$PLUGINSDIR\iospecial.ini" "Field 6" "HWND"
  SetCtlColors $0 0x000000 0xFFFFFF
FunctionEnd

Function Startup_Leave
  ReadINIStr $0 "$PLUGINSDIR\iospecial.ini" "Field 6" "State"
  StrCmp $0 "0" +3
  SetShellVarContext current
  CreateShortCut "$SMSTARTUP\${PRODUCT_NAME}.lnk" "$INSTDIR\${PROGEXE}" "--start-minimized"
FunctionEnd

Function un.onInit
  MessageBox MB_ICONQUESTION|MB_YESNO|MB_DEFBUTTON2 "Are you sure you want to uninstall $(^Name)?" IDYES +2
  Abort
  !insertmacro MULTIUSER_UNINIT
FunctionEnd

Function un.onUninstSuccess
  HideWindow
  MessageBox MB_ICONINFORMATION|MB_OK "$(^Name) was successfully removed from your computer."
FunctionEnd


Section "MainSection" SEC01
  SetOutPath "$INSTDIR"
  SetOverwrite ifnewer
  File "${PROGEXE}"
  SetOverwrite off
  File "${BASENAME}.ini"
  SetOverwrite ifnewer
  File "README.txt"
  CreateDirectory "$SMPROGRAMS\${PRODUCT_NAME}"
  CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\${PRODUCT_NAME}.lnk" "$INSTDIR\${PROGEXE}"
  CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\README.lnk" "$INSTDIR\README.txt"
SectionEnd

Section -AdditionalIcons
  WriteIniStr "$INSTDIR\${PRODUCT_NAME}.url" "InternetShortcut" "URL" "${PRODUCT_WEB_SITE}"
  CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\Website.lnk" "$INSTDIR\${PRODUCT_NAME}.url"
  CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\Uninstall ${PRODUCT_NAME}.lnk" "$INSTDIR\${UNINSTALL_FILENAME}"
SectionEnd

Section -Post
  WriteUninstaller "$INSTDIR\${UNINSTALL_FILENAME}"
  !insertmacro MULTIUSER_RegistryAddInstallInfo

  WriteRegStr SHCTX "${PRODUCT_DIR_REGKEY}" "" "$INSTDIR\${PROGEXE}"
  WriteRegStr SHCTX "${PRODUCT_UNINST_KEY}" "DisplayName" "$(^Name)"
  WriteRegStr SHCTX "${PRODUCT_UNINST_KEY}" "UninstallString" "$INSTDIR\${UNINSTALL_FILENAME}"
  WriteRegStr SHCTX "${PRODUCT_UNINST_KEY}" "DisplayIcon" "$INSTDIR\${PROGEXE}"
  WriteRegStr SHCTX "${PRODUCT_UNINST_KEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr SHCTX "${PRODUCT_UNINST_KEY}" "URLInfoAbout" "${PRODUCT_WEB_SITE}"
  WriteRegStr SHCTX "${PRODUCT_UNINST_KEY}" "Publisher" "${PRODUCT_PUBLISHER}"
SectionEnd

Section Uninstall
  SetAutoClose true
  ${nsProcess::KillProcess} "${PROGEXE}" $R4

  Delete "$INSTDIR\${PRODUCT_NAME}.url"
  Delete "$INSTDIR\${UNINSTALL_FILENAME}"
  Delete "$INSTDIR\README.txt"
  Delete "$INSTDIR\${BASENAME}.ini"

  Delete "$SMPROGRAMS\${PRODUCT_NAME}\${PRODUCT_NAME}.lnk"
  Delete "$SMPROGRAMS\${PRODUCT_NAME}\README.lnk"
  Delete "$SMPROGRAMS\${PRODUCT_NAME}\Website.lnk"
  Delete "$SMPROGRAMS\${PRODUCT_NAME}\Uninstall ${PRODUCT_NAME}.lnk"
  RMDir "$SMPROGRAMS\${PRODUCT_NAME}"

  Delete "$INSTDIR\${PROGEXE}"
  RMDir "$INSTDIR"

  DeleteRegKey SHCTX "${PRODUCT_UNINST_KEY}"
  DeleteRegKey SHCTX "${PRODUCT_DIR_REGKEY}"
  !insertmacro MULTIUSER_RegistryRemoveInstallInfo
  Call un.RefreshSysTray

  SetShellVarContext current
  Delete "$LOCALAPPDATA\${PRODUCT_NAME}\${BASENAME}.ini"
  RmDir  "$LOCALAPPDATA\${PRODUCT_NAME}"
  Delete "$SMSTARTUP\${PRODUCT_NAME}.lnk"
SectionEnd
