// Optional first-party source adaptation of the independently executed native
// readback runner. Requires a separately licensed AutoCAD2026/.NET8 installation.
// No Autodesk DLL/SDK, source drawing, font or private project identity is bundled.
using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using System.Security.Cryptography;
using System.Text.Json;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Autodesk.AutoCAD.Runtime;
using AcApp=Autodesk.AutoCAD.ApplicationServices.Core.Application;

public class AuditJob {
 public string input_dwg {get;set;}
 public string input_sha256 {get;set;}
 public string output_root {get;set;}
 public string[] expected_native_arrow_handles {get;set;}
 public Dictionary<string,string> expected_font_sha256_by_basename {get;set;}
}

public class PortableNativeAudit {
 static string Hash(string p) {using(var f=new FileStream(p,FileMode.Open,FileAccess.Read,FileShare.ReadWrite))using(var h=SHA256.Create())return BitConverter.ToString(h.ComputeHash(f)).Replace("-","").ToLowerInvariant();}
 static Dictionary<string,object> D(){return new Dictionary<string,object>();}
 static object Fonts(Database db,Transaction tr,HashSet<ObjectId> used,AuditJob job) {
  var rows=new List<object>();
  foreach(var id in used) {
   var style=(TextStyleTableRecord)tr.GetObject(id,OpenMode.ForRead);
   foreach(var part in new[]{new[]{"font",style.FileName},new[]{"bigfont",style.BigFontFileName}}) {
    if(String.IsNullOrWhiteSpace(part[1]))continue;
    string actual=HostApplicationServices.Current.FindFile(part[1],db,FindFileHint.FontFile);
    if(!File.Exists(actual))throw new FileNotFoundException("Native font could not be resolved",actual);
    string digest=Hash(actual);bool bound=false;
    if(job.expected_font_sha256_by_basename!=null) {
     var exp=job.expected_font_sha256_by_basename.FirstOrDefault(k=>String.Equals(k.Key,Path.GetFileName(actual),StringComparison.OrdinalIgnoreCase));
     if(exp.Key!=null){if(exp.Value!=digest)throw new InvalidOperationException("Resolved native font differs from explicit expected hash");bound=true;}
    }
    rows.Add(new {style=style.Name,kind=part[0],requested=part[1],host_resolved_path=actual,sha256=digest,expected_identity_bound=bound});
   }
  }
  return rows;
 }
 static Dictionary<string,object> Content(Database db,AuditJob job) {
  var result=D();var text=new List<object>();var identities=new List<object>();var used=new HashSet<ObjectId>();int bad=0;
  using(var tr=db.TransactionManager.StartTransaction()) {
   var bt=(BlockTable)tr.GetObject(db.BlockTableId,OpenMode.ForRead);var ms=(BlockTableRecord)tr.GetObject(bt[BlockTableRecord.ModelSpace],OpenMode.ForRead);
   foreach(ObjectId id in ms) {
    var e=(Entity)tr.GetObject(id,OpenMode.ForRead);var x=new List<object>();
    using(var rb=e.XData) {if(rb!=null)foreach(var t in rb.AsArray())x.Add(new {code=t.TypeCode,value=t.Value==null?null:t.Value.ToString()});}
    identities.Add(new {handle=e.Handle.ToString(),type=e.GetType().Name,layer=e.Layer,xdata=x});
    var t1=e as DBText;var t2=e as MText;if(t1==null && t2==null)continue;
    var row=D();row["handle"]=e.Handle.ToString();row["raw_text"]=t1!=null?t1.TextString:t2.Contents;row["layer"]=e.Layer;
    ObjectId style=t1!=null?t1.TextStyleId:t2.TextStyleId;used.Add(style);row["text_style_handle"]=style.Handle.ToString();
    if(t1!=null){row["height"]=t1.Height;row["width_factor"]=t1.WidthFactor;row["rotation"]=t1.Rotation;row["position"]=new[]{t1.Position.X,t1.Position.Y,t1.Position.Z};}
    else {row["text_height"]=t2.TextHeight;row["specified_width"]=t2.Width;row["actual_width"]=t2.ActualWidth;row["actual_height"]=t2.ActualHeight;row["rotation"]=t2.Rotation;row["location"]=new[]{t2.Location.X,t2.Location.Y,t2.Location.Z};}
    try {var b=e.GeometricExtents;row["native_extents"]=new[]{b.MinPoint.X,b.MinPoint.Y,b.MinPoint.Z,b.MaxPoint.X,b.MaxPoint.Y,b.MaxPoint.Z};row["extents_ok"]=true;}
    catch(System.Exception error){row["extents_ok"]=false;row["extents_error"]=error.Message;if(!String.IsNullOrWhiteSpace(t1!=null?t1.TextString:t2.Text))bad++;}
    text.Add(row);
   }
   var table=(DrawOrderTable)tr.GetObject(ms.DrawOrderTableId,OpenMode.ForRead);
   var order=table.GetFullDrawOrder((byte)0).Cast<ObjectId>().Select(id=>id.Handle.ToString()).ToArray();
   var plotOrder=table.GetFullDrawOrder((byte)32).Cast<ObjectId>().Select(id=>id.Handle.ToString()).ToArray();
   if(order.Length!=identities.Count || order.Distinct(StringComparer.OrdinalIgnoreCase).Count()!=identities.Count)throw new InvalidOperationException("Native draw order is not a complete unique ModelSpace order");
   bool arrowsBound=job.expected_native_arrow_handles!=null && job.expected_native_arrow_handles.Length>0;
   if(arrowsBound) {
    var required=job.expected_native_arrow_handles;
    if(required.Distinct(StringComparer.OrdinalIgnoreCase).Count()!=required.Length || !order.Skip(order.Length-required.Length).SequenceEqual(required,StringComparer.OrdinalIgnoreCase) || !order.SequenceEqual(plotOrder,StringComparer.OrdinalIgnoreCase))throw new InvalidOperationException("Explicit actual-DWG arrow handles are not the final plot-enabled draw-order objects");
   }
   result["native_text_extents"]=text;result["meaningful_text_extents_failures"]=bad;result["actual_entity_identity_xdata"]=identities;
   result["native_draw_order_bottom_to_top"]=order;result["native_plot_draw_order_bottom_to_top"]=plotOrder;result["arrow_order_identity_bound"]=arrowsBound;
   result["native_font_resolution"]=Fonts(db,tr,used,job);result["draw_order_table_handle"]=table.Handle.ToString();tr.Commit();
  }
  return result;
 }
 [CommandMethod("PFDAUDIT")]
 public static void Audit() {
  AuditJob job=null;OwnedNativeAuditOutput ownedOutput=null;var report=D();report["success"]=false;
  try {
   if(Convert.ToInt32(AcApp.GetSystemVariable("REPORTERROR"))!=0)throw new InvalidOperationException("REPORTERROR must already be0 before native processing");
   string path=Environment.GetEnvironmentVariable("PFD_NATIVE_AUDIT_JOB");if(String.IsNullOrWhiteSpace(path))throw new InvalidOperationException("Explicit PFD_NATIVE_AUDIT_JOB required");
   job=JsonSerializer.Deserialize<AuditJob>(File.ReadAllText(path));
   if(!Path.IsPathFullyQualified(job.input_dwg) || !Path.IsPathFullyQualified(job.output_root))throw new InvalidOperationException("Absolute explicit input and output root required");
   ownedOutput=OwnedNativeAuditOutput.Create(job.output_root);
   string output=ownedOutput.StrictDxfPath;
   report["native_output_ownership"]="new directory atomically created; receipt handle reserved CreateNew; DXF published CreateNew";
   report["native_dxfout_temporary_path"]=ownedOutput.NativeDxfTempPath;
   string before=Hash(job.input_dwg);if(before!=job.input_sha256)throw new InvalidOperationException("Actual input DWG hash differs from explicit contract");
   report["input_dwg_sha256_before"]=before;report["database_assembly"]=typeof(Database).Assembly.FullName;report["REPORTERROR"]=AcApp.GetSystemVariable("REPORTERROR").ToString();report["SECURELOAD"]=AcApp.GetSystemVariable("SECURELOAD").ToString();report["TRUSTEDPATHS"]=AcApp.GetSystemVariable("TRUSTEDPATHS").ToString();
   using(var db=new Database(false,true)) {
    db.ReadDwgFile(job.input_dwg,FileOpenMode.OpenForReadAndReadShare,false,"");db.CloseInput(true);
    report["original_native_version"]=db.OriginalFileVersion.ToString();report["content"]=Content(db,job);db.DxfOut(ownedOutput.NativeDxfTempPath,16,DwgVersion.AC1032);
   }
   ownedOutput.PublishDxf();
   string after=Hash(job.input_dwg);report["input_dwg_sha256_after"]=after;if(before!=after)throw new InvalidOperationException("Input DWG bytes changed during readback");
   report["strict_dxf_path"]=output;report["strict_dxf_sha256"]=Hash(output);
   if(Convert.ToInt32(((Dictionary<string,object>)report["content"])["meaningful_text_extents_failures"])!=0)throw new InvalidOperationException("Some meaningful text native extents unavailable");
   report["success"]=true;
  } catch(System.Exception error){report["error_type"]=error.GetType().FullName;report["error"]=error.ToString();}
  finally {
   try {if(ownedOutput!=null)ownedOutput.WriteReceipt(JsonSerializer.Serialize(report,new JsonSerializerOptions{WriteIndented=true}));}
   catch(System.Exception error){report["receipt_write_error"]=error.ToString();report["success"]=false;}
   finally {if(ownedOutput!=null)ownedOutput.Dispose();}
   AcApp.DocumentManager.MdiActiveDocument.Editor.WriteMessage("\nPFD_NATIVE_AUDIT "+JsonSerializer.Serialize(report)+"\n");
  }
 }
}
