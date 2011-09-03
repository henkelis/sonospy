
set ws = CreateObject("WScript.Shell")

cmds = ws.Run("sonospy_p.cmd",0,False)

cmds = ws.Run("sonospy_w.cmd",0,False)

set ws = Nothing


