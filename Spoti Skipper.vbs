' Spoti Skipper: start in the system tray, no console window.
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
py = root & "\listener\.venv\Scripts\pythonw.exe"
If Not fso.FileExists(py) Then py = "pythonw.exe"
sh.CurrentDirectory = root & "\listener"
sh.Run """" & py & """ """ & root & "\listener\tray.py""", 0, False
