"""Emit a reviewable gated CoreConsole script; never launches CAD or deploys DLLs."""
from pathlib import Path
import argparse,hashlib,json

def script(dll):
    q=lambda v:json.dumps(v,ensure_ascii=True)
    target=Path(dll).resolve().as_posix()
    return '\n'.join([
        '(setq PFD_REPORT_SET (vl-catch-all-apply \'setvar (list "REPORTERROR" 0)))',
        '(setq PFD_REPORT_READ (vl-catch-all-apply \'getvar (list "REPORTERROR")))',
        '(princ "\\nPFD_REPORTERROR=")(prin1 PFD_REPORT_READ)(princ "\\n")',
        '(setq PFD_SECURE (getvar "SECURELOAD"))',
        '(setq PFD_TRUST (getvar "TRUSTEDPATHS"))',
        '(setq PFD_PROJECT (getvar "PROJECTAWARE"))',
        '(setq PFD_FOUND (vl-catch-all-apply \'findtrustedfile (list '+q(target)+')))',
        '(princ "\\nPFD_SECURITY=")(prin1 (list PFD_SECURE PFD_TRUST PFD_PROJECT PFD_FOUND))(princ "\\n")',
        '(if (and (not (vl-catch-all-error-p PFD_REPORT_SET)) (equal PFD_REPORT_READ 0) (member PFD_SECURE \'(1 2)) (member PFD_PROJECT \'(0 1)) (eq (type PFD_FOUND) \'STR) (equal (strcase (vl-string-translate '+q(chr(92))+' "/" PFD_FOUND)) (strcase '+q(target)+'))) (progn (princ "\\nPFD_NATIVE_GATE_PASS\\n") (command "_.NETLOAD" '+q(target)+') (command "PFDAUDIT")) (princ "\\nPFD_NATIVE_GATE_FAIL_NO_NETLOAD\\n"))',
        '(command "_.QUIT" "_N")',''])

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--dll',type=Path,required=True);ap.add_argument('--expected-dll-sha256',required=True);ap.add_argument('--out',type=Path,required=True);args=ap.parse_args()
    digest=hashlib.sha256(args.dll.read_bytes()).hexdigest()
    if digest!=args.expected_dll_sha256:raise SystemExit('DLL differs from explicitly reviewed bytes')
    if args.out.exists():raise SystemExit('Refuse overwrite of prior native script')
    args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(script(args.dll),'ascii')
    print(json.dumps({'script':str(args.out),'dll_sha256':digest,'cad_executed':False,'security_variables_changed':False,'required_before_use':'Deploy only reviewed bytes into an already trusted exact tool directory; set explicit PFD_NATIVE_AUDIT_JOB; use a separate isolated CoreConsole profile. Monitor reporter processes and stop without retries on any native abnormality.'},indent=2))

if __name__=='__main__':main()
