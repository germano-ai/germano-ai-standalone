"""Conversione .doc/.ppt <-> .docx/.pptx con Microsoft Office, eseguita in un processo separato.

Uso: python office_convert.py <word|powerpoint> <origine> <destinazione> <formato>
- DispatchEx: istanza dedicata, il Word gia' aperto dall'utente non viene mai toccato.
- Macro disattivate (AutomationSecurity = ForceDisable).
- Il processo chiamante applica un timeout e termina eventuali istanze bloccate.
"""
import os
import sys


def main():
    app, src, dst, fmt = sys.argv[1], os.path.abspath(sys.argv[2]), os.path.abspath(sys.argv[3]), int(sys.argv[4])
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    obj = None
    try:
        if app == "word":
            obj = win32com.client.DispatchEx("Word.Application")
            obj.Visible = False
            obj.DisplayAlerts = 0
            try:
                obj.AutomationSecurity = 3
            except Exception:
                pass
            # Password fittizia: un documento protetto fallisce subito invece di aprire una finestra invisibile.
            doc = obj.Documents.Open(src, ConfirmConversions=False, ReadOnly=True, AddToRecentFiles=False,
                                     PasswordDocument="germano-no-password", Visible=False, NoEncodingDialog=True)
            try:
                doc.SaveAs2(dst, FileFormat=fmt)
            except Exception:
                doc.SaveAs(dst, fmt)
            doc.Close(False)
        elif app == "powerpoint":
            obj = win32com.client.DispatchEx("PowerPoint.Application")
            try:
                obj.AutomationSecurity = 3
            except Exception:
                pass
            pres = obj.Presentations.Open(src, ReadOnly=True, Untitled=False, WithWindow=False)
            pres.SaveAs(dst, fmt)
            pres.Close()
        else:
            raise SystemExit(f"applicazione non supportata: {app}")
    finally:
        if obj is not None:
            try:
                obj.Quit()
            except Exception:
                pass
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        print(f"{type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
