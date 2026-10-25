// Bounded Windows output ownership for the optional AutoCAD read-only audit.
// No AutoCAD dependency; existing directories and existing files are never reused.
using System;
using System.IO;
using System.Text;
using System.ComponentModel;
using System.Runtime.InteropServices;

public sealed class OwnedNativeAuditOutput : IDisposable {
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)]
 [return:MarshalAs(UnmanagedType.Bool)]
 static extern bool CreateDirectoryW(string path,IntPtr securityAttributes);
 readonly FileStream receipt;
 bool receiptWritten;
 public string Root {get;private set;}
 public string StrictDxfPath {get;private set;}
 public string NativeDxfTempPath {get;private set;}
 public string ReceiptPath {get;private set;}

 OwnedNativeAuditOutput(string root) {
  if(!Path.IsPathFullyQualified(root))throw new InvalidOperationException("Absolute new output directory required");
  Root=Path.GetFullPath(root);
  StrictDxfPath=NativeWriteGuard.RequireWithin(Root,Path.Combine(Root,"strict-readback.dxf"));
  ReceiptPath=NativeWriteGuard.RequireWithin(Root,Path.Combine(Root,"native-audit.json"));
  NativeDxfTempPath=NativeWriteGuard.RequireWithin(Root,Path.Combine(Root,"native-dxfout-"+Guid.NewGuid().ToString("N")+".dxf"));
  // Unlike Directory.CreateDirectory, this Windows primitive fails atomically
  // if another actor has already created the output directory or a same-name file.
  if(!CreateDirectoryW(Root,IntPtr.Zero))throw new Win32Exception(Marshal.GetLastWin32Error(),"Refuse existing/unavailable native output directory");
  receipt=new FileStream(ReceiptPath,FileMode.CreateNew,FileAccess.Write,FileShare.None);
 }
 public static OwnedNativeAuditOutput Create(string root) {return new OwnedNativeAuditOutput(root);}

 public void PublishDxf() {
  // AutoCAD DxfOut writes only to the fresh unpredictable temporary name.
  // Publishing the exact native bytes is exclusive: no existing target is replaced.
  using(var source=new FileStream(NativeDxfTempPath,FileMode.Open,FileAccess.Read,FileShare.Read))
  using(var target=new FileStream(StrictDxfPath,FileMode.CreateNew,FileAccess.Write,FileShare.None)) {
   source.CopyTo(target);target.Flush(true);
  }
 }
 public void WriteReceipt(string json) {
  if(receiptWritten)throw new InvalidOperationException("Receipt already written by this run");
  byte[] bytes=new UTF8Encoding(false).GetBytes(json);
  receipt.Write(bytes,0,bytes.Length);receipt.Flush(true);receiptWritten=true;
 }
 public void Dispose(){receipt.Dispose();}
}
