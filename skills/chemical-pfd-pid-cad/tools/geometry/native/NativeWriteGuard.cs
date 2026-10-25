// Pure .NET path guard; no AutoCAD dependency. Shared with offline unit tests.
using System;
using System.IO;
public static class NativeWriteGuard {
 public static string RequireWithin(string root, string path) {
  if(String.IsNullOrWhiteSpace(root) || String.IsNullOrWhiteSpace(path) || !Path.IsPathFullyQualified(root) || !Path.IsPathFullyQualified(path)) throw new InvalidOperationException("Absolute explicit native output root/path required");
  string canonicalRoot=Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar,Path.AltDirectorySeparatorChar)+Path.DirectorySeparatorChar;
  string canonicalPath=Path.GetFullPath(path);
  if(!canonicalPath.StartsWith(canonicalRoot,StringComparison.OrdinalIgnoreCase)) throw new InvalidOperationException("Output outside explicit native run: "+canonicalPath);
  return canonicalPath;
 }
}
