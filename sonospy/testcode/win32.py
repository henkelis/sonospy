import win32com.client
strComputer = "."
objWMIService = win32com.client.Dispatch("WbemScripting.SWbemLocator")
objSWbemServices = objWMIService.ConnectServer(strComputer,"root\cimv2")
colItems = objSWbemServices.ExecQuery("Select * from Win32_NetworkAdapter")
for objItem in colItems:
    print "Adapter Type: ", objItem.AdapterType
    print "Adapter Type Id: ", objItem.AdapterTypeId
    print "AutoSense: ", objItem.AutoSense
    print "Availability: ", objItem.Availability
    print "Caption: ", objItem.Caption
    print "Config Manager Error Code: ", objItem.ConfigManagerErrorCode
    print "Config Manager User Config: ", objItem.ConfigManagerUserConfig
    print "Creation Class Name: ", objItem.CreationClassName
    print "Description: ", objItem.Description
    print "Device ID: ", objItem.DeviceID
    print "Error Cleared: ", objItem.ErrorCleared
    print "Error Description: ", objItem.ErrorDescription
    print "Index: ", objItem.Index
    print "Install Date: ", objItem.InstallDate
    print "Installed: ", objItem.Installed
    print "Last Error Code: ", objItem.LastErrorCode
    print "MAC Address: ", objItem.MACAddress
    print "Manufacturer: ", objItem.Manufacturer
    print "Max Number Controlled: ", objItem.MaxNumberControlled
    print "Max Speed: ", objItem.MaxSpeed
    print "Name: ", objItem.Name
    print "Net Connection ID: ", objItem.NetConnectionID
    print "Net Connection Status: ", objItem.NetConnectionStatus
    z = objItem.NetworkAddresses
    if z is None:
        a = 1
    else:
        for x in z:
            print "Network Addresses: ", x
    print "Permanent Address: ", objItem.PermanentAddress
    print "PNP Device ID: ", objItem.PNPDeviceID
    z = objItem.PowerManagementCapabilities
    if z is None:
        a = 1
    else:
        for x in z:
            print "Power Management Capabilities: ", x
    print "Power Management Supported: ", objItem.PowerManagementSupported
    print "Product Name: ", objItem.ProductName
    print "Service Name: ", objItem.ServiceName
    print "Speed: ", objItem.Speed
    print "Status: ", objItem.Status
    print "Status Info: ", objItem.StatusInfo
    print "System Creation Class Name: ", objItem.SystemCreationClassName
    print "System Name: ", objItem.SystemName
    print "Time Of Last Reset: ", objItem.TimeOfLastReset

