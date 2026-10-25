using System;
using System.IO;
public class NativeWriteGuardTest {
 static int count=0;
 static void Check(string name,string root,string path,bool reject) {
  bool refused=false;try{NativeWriteGuard.RequireWithin(root,path);}catch(InvalidOperationException){refused=true;}
  if(refused!=reject)throw new Exception("Unexpected guard result: "+name);count++;
 }
 public static void Main() {
  string r=Path.Combine(Path.GetPathRoot(Environment.CurrentDirectory),"portable-audit-test","run");
  Check("inside",r,Path.Combine(r,"stage","receipt.json"),false);
  Check("unicode",r,Path.Combine(r,"stage","bridge-桥.json"),false);
  Check("parent",r,Path.Combine(r,"..","outside.json"),true);
  Check("prefix-sibling",r,r+"-other"+Path.DirectorySeparatorChar+"receipt.json",true);
  Check("root-itself",r,r,true);
  Check("relative-path",r,"relative.json",true);
  Check("relative-root","relative",Path.Combine(r,"receipt.json"),true);
  Console.WriteLine("PURE_PATH_GUARD_PASS="+count);
 }
}
