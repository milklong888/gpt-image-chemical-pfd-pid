// Effective filesystem tests of the exact helper consumed by NativeAudit.
// No Autodesk references or AutoCAD process; all bytes are original test fixtures.
using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;

class OwnedNativeAuditOutputTest {
 static readonly List<string> passed=new List<string>();
 static void Check(bool ok,string name){if(!ok)throw new Exception("FAIL: "+name);passed.Add(name);Console.WriteLine("PASS "+name);}
 static bool Refused(Action action){try{action();return false;}catch(IOException){return true;}catch(System.ComponentModel.Win32Exception){return true;}catch(InvalidOperationException){return true;}}
 static string New(string baseDir,string name){return Path.Combine(baseDir,name);}
 public static int Main(string[] args) {
  try {
   string b=Path.GetFullPath(args[0]);Directory.CreateDirectory(b);
   string old=New(b,"old-success");Directory.CreateDirectory(old);
   string receipt=New(old,"native-audit.json"),dxf=New(old,"strict-readback.dxf");
   File.WriteAllText(receipt,"ORIGINAL SUCCESS RECEIPT");File.WriteAllText(dxf,"ORIGINAL NATIVE DXF");
   Check(Refused(()=>{using(var o=OwnedNativeAuditOutput.Create(old))o.WriteReceipt("BAD");}),"existing_success_directory_refused");
   Check(File.ReadAllText(receipt)=="ORIGINAL SUCCESS RECEIPT" && File.ReadAllText(dxf)=="ORIGINAL NATIVE DXF" && Directory.GetFiles(old).Length==2,"old_receipt_and_dxf_bytes_unchanged");
   string empty=New(b,"old-empty");Directory.CreateDirectory(empty);
   Check(Refused(()=>{using(var o=OwnedNativeAuditOutput.Create(empty)){};}) && Directory.GetFileSystemEntries(empty).Length==0,"existing_empty_directory_refused_without_write");
   string rootFile=New(b,"root-is-file");File.WriteAllText(rootFile,"KEEP ROOT FILE");
   Check(Refused(()=>{using(var o=OwnedNativeAuditOutput.Create(rootFile)){};}) && File.ReadAllText(rootFile)=="KEEP ROOT FILE","existing_root_file_refused_unchanged");
   string targetDir=New(b,"existing-target-directory");Directory.CreateDirectory(New(targetDir,"strict-readback.dxf"));
   File.WriteAllText(New(targetDir,"native-audit.json"),"KEEP TARGET-DIR RECEIPT");
   Check(Refused(()=>{using(var o=OwnedNativeAuditOutput.Create(targetDir)){};}) && File.ReadAllText(New(targetDir,"native-audit.json"))=="KEEP TARGET-DIR RECEIPT","existing_target_directory_refused_unchanged");
   string fresh=New(b,"fresh-success");
   using(var o=OwnedNativeAuditOutput.Create(fresh)) {
    Check(Refused(()=>File.WriteAllText(o.ReceiptPath,"FOREIGN WRITE")),"receipt_create_new_exclusive_handle");
    File.WriteAllText(o.NativeDxfTempPath,"SYNTHETIC NATIVE-BYTE COPY CONTROL");o.PublishDxf();
    Check(File.ReadAllText(o.StrictDxfPath)=="SYNTHETIC NATIVE-BYTE COPY CONTROL","exclusive_dxf_publish_preserves_exact_bytes");
    o.WriteReceipt("{\"success\":true}");
    Check(Refused(()=>o.WriteReceipt("SECOND WRITE")),"owned_receipt_written_at_most_once");
   }
   Check(File.ReadAllText(New(fresh,"native-audit.json"))=="{\"success\":true}","successful_receipt_persisted_exactly");
   Check(Refused(()=>{using(var o=OwnedNativeAuditOutput.Create(fresh)){};}) && File.ReadAllText(New(fresh,"native-audit.json"))=="{\"success\":true}","repeat_attempt_cannot_replace_success");
   string conflict=New(b,"publish-conflict");
   using(var o=OwnedNativeAuditOutput.Create(conflict)) {
    File.WriteAllText(o.NativeDxfTempPath,"OWN TEMP");File.WriteAllText(o.StrictDxfPath,"FOREIGN TARGET");
    Check(Refused(()=>o.PublishDxf()) && File.ReadAllText(o.StrictDxfPath)=="FOREIGN TARGET","create_new_dxf_refuses_late_target_without_overwrite");
    o.WriteReceipt("{\"success\":false,\"reason\":\"publish conflict\"}");
   }
   Check(File.ReadAllText(New(conflict,"native-audit.json")).Contains("publish conflict"),"exception_receipt_only_to_owned_stream");
   // Independent control reproduces the old try/finally pattern. It is not
   // represented as executing the AutoCAD-dependent NativeAudit command.
   string control=New(b,"old-pattern-control.json");File.WriteAllText(control,"OLD SUCCESS");
   try{try{if(File.Exists(control))throw new IOException("Refuse overwrite");}finally{File.WriteAllText(control,"OVERWRITTEN FAILURE");}}catch(IOException){}
   Check(File.ReadAllText(control)=="OVERWRITTEN FAILURE","old_pattern_control_reproduces_receipt_loss");
   Console.WriteLine("OWNED_NATIVE_OUTPUT_PASS="+passed.Count);return 0;
  }catch(Exception error){Console.Error.WriteLine(error);return 1;}
 }
}
