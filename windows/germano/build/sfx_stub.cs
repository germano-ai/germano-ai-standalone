// Germano AI - avviatore dell'installer in un solo file (germano-<versione>.exe, germano-client-<versione>.exe).
//
// Compilato da costruisci_installer_windows.py con il compilatore C# di .NET Framework 4, gia' presente in ogni
// Windows 10/11 (nessun SDK da installare; sintassi C# 5). In coda all'eseguibile ci sono:
//   1. il "kit": un archivio ZIP con l'interprete Python minimo e germano_install.py (l'installer vero e proprio);
//   2. l'archivio ZIP con tutti i file del programma (runtime, modelli IA, interfaccia);
//   3. una coda di 48 byte: firma "GERMANO.SFX.0001" e posizione/lunghezza (64 bit) del kit e dell'archivio.
//
// Permessi (suite): appena si apre, l'avviatore si riavvia SUBITO con i permessi di amministratore (richiesta UAC di
// Windows con il nome e l'icona di questo installer), perche' l'installazione consente l'accesso dalla rete locale
// (regola del firewall di Windows). La copia elevata estrae il kit e installa; questa copia, con i permessi normali,
// attende la fine e apre Germano (che quindi non gira mai come amministratore). Alla copia elevata passa le cartelle e
// il SID dell'utente (--user-context): se i permessi sono stati dati con le credenziali di un altro account, il
// programma si installa comunque per l'utente che ha avviato l'installazione. Gli aggiornamenti avviati da Germano
// (--update) e il client non chiedono permessi. Collaudo senza UAC: variabile GERMANO_SETUP_NO_ELEVATION=1.
//
// L'avviatore estrae solo il kit in una cartella temporanea, avvia l'installer passandogli il percorso di questo
// .exe (da cui l'installer legge direttamente l'archivio, senza copie intermedie), attende la fine, apre il programma
// indicato dall'installer (--launch-file), elimina la cartella temporanea e restituisce lo stesso codice di uscita
// (0 riuscito, 1 errore, 2 annullato).
using System;
using System.ComponentModel;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Principal;
using System.Text;
using System.Threading;
using System.Windows.Forms;

[assembly: AssemblyTitle("@TITLE@")]
[assembly: AssemblyDescription("@TITLE@")]
[assembly: AssemblyProduct("@PRODUCT@")]
[assembly: AssemblyCompany("germano.ai")]
[assembly: AssemblyCopyright("germano.ai - GNU GPL v3")]
[assembly: AssemblyVersion("@VERSION4@")]
[assembly: AssemblyFileVersion("@VERSION4@")]
[assembly: AssemblyInformationalVersion("@VERSION@")]

static class GermanoSetup
{
    const string Magic = "GERMANO.SFX.0001";
    const int TrailerSize = 48;
    // suite: true (regola del firewall per la rete locale); client: false (non serve nessun permesso speciale)
    static readonly bool ElevateForInstall = @ELEVATE@;

    [STAThread]
    static int Main(string[] args)
    {
        Application.EnableVisualStyles();
        bool it = CultureInfo.CurrentUICulture.TwoLetterISOLanguageName == "it";
        if (!Environment.Is64BitOperatingSystem)
        {
            Fail(it ? "Germano AI richiede Windows 10 o 11 a 64 bit." : "Germano AI requires 64-bit Windows 10 or 11.");
            return 1;
        }
        string exe = Assembly.GetExecutingAssembly().Location;
        bool child = HasArg(args, "--elevated");
        bool update = HasArg(args, "--update");
        bool noElevation = Environment.GetEnvironmentVariable("GERMANO_SETUP_NO_ELEVATION") == "1";
        if (ElevateForInstall && !child && !update && !noElevation && !IsElevated())
            return RunElevated(exe, args, it);
        return RunInstaller(exe, args, it);
    }

    // Copia non elevata: chiede subito i permessi, attende la copia elevata e alla fine apre Germano.
    static int RunElevated(string exe, string[] args, bool it)
    {
        string work = Path.Combine(Path.GetTempPath(), "germano-setup-" + Guid.NewGuid().ToString("N").Substring(0, 12));
        Directory.CreateDirectory(work);
        try
        {
            string context = Path.Combine(work, "utente.json");
            File.WriteAllText(context, UserContextJson(), new UTF8Encoding(false));
            string launch = Path.Combine(work, "avvio.txt");
            StringBuilder cmd = new StringBuilder("--elevated");
            cmd.Append(' ').Append(Quote("--user-context=" + context));
            cmd.Append(' ').Append(Quote("--launch-file=" + launch));
            // lingua di chi ha avviato l'installer (non quella dell'eventuale altro account che concede i permessi)
            if (ArgValue(args, "--lang") == null && !HasArg(args, "--lang")) cmd.Append(" --lang=").Append(it ? "it" : "en");
            foreach (string a in args) cmd.Append(' ').Append(Quote(a));
            ProcessStartInfo psi = new ProcessStartInfo(exe, cmd.ToString());
            psi.UseShellExecute = true;
            psi.Verb = "runas";
            psi.WorkingDirectory = Path.GetDirectoryName(exe);
            Process p;
            try
            {
                p = Process.Start(psi);
            }
            catch (Win32Exception ex)
            {
                if (ex.NativeErrorCode != 1223) throw;      // 1223 = richiesta UAC rifiutata
                MessageBox.Show(it
                    ? "Per installare Germano AI servono i permessi di amministratore: servono a consentire l'accesso dalla rete locale (regola del firewall di Windows).\n\nAvvia di nuovo l'installer e scegli «Sì»."
                    : "Installing Germano AI requires administrator permission: it is needed to allow access from the local network (Windows Firewall rule).\n\nStart the installer again and choose \"Yes\".",
                    "Germano AI", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return 2;
            }
            if (p == null) return 1;
            using (p)
            {
                p.WaitForExit();
                int code = p.ExitCode;
                LaunchFromFile(launch, false);
                return code;
            }
        }
        catch (Exception ex)
        {
            Fail((it ? "Impossibile avviare l'installazione di Germano AI:\n\n" : "Cannot start the Germano AI setup:\n\n")
                 + ex.Message);
            return 1;
        }
        finally
        {
            Cleanup(work);
        }
    }

    // Installazione vera e propria: kit in una cartella temporanea e installer Python.
    static int RunInstaller(string exe, string[] args, bool it)
    {
        string temp = null;
        try
        {
            byte[] kit;
            using (FileStream fs = new FileStream(exe, FileMode.Open, FileAccess.Read, FileShare.Read))
            {
                if (fs.Length < TrailerSize) throw new InvalidDataException();
                fs.Seek(-TrailerSize, SeekOrigin.End);
                BinaryReader br = new BinaryReader(fs);
                string magic = Encoding.ASCII.GetString(br.ReadBytes(16));
                long kitOff = br.ReadInt64(), kitLen = br.ReadInt64(), payOff = br.ReadInt64(), payLen = br.ReadInt64();
                long end = fs.Length - TrailerSize;
                if (magic != Magic || kitOff <= 0 || kitLen <= 0 || kitLen > int.MaxValue || kitOff + kitLen > end
                    || payOff <= 0 || payLen <= 0 || payOff + payLen > end)
                    throw new InvalidDataException();
                fs.Seek(kitOff, SeekOrigin.Begin);
                kit = br.ReadBytes((int)kitLen);
                if (kit.Length != kitLen) throw new InvalidDataException();
            }

            temp = Path.Combine(Path.GetTempPath(), "germano-setup-" + Guid.NewGuid().ToString("N").Substring(0, 12));
            Directory.CreateDirectory(temp);
            string root = Path.GetFullPath(temp) + Path.DirectorySeparatorChar;
            using (ZipArchive zip = new ZipArchive(new MemoryStream(kit), ZipArchiveMode.Read))
            {
                foreach (ZipArchiveEntry entry in zip.Entries)
                {
                    string dest = Path.GetFullPath(Path.Combine(temp, entry.FullName.Replace('/', Path.DirectorySeparatorChar)));
                    if (!dest.StartsWith(root, StringComparison.OrdinalIgnoreCase)) throw new InvalidDataException();
                    if (entry.FullName.EndsWith("/")) { Directory.CreateDirectory(dest); continue; }
                    Directory.CreateDirectory(Path.GetDirectoryName(dest));
                    using (Stream src = entry.Open())
                    using (FileStream dst = File.Create(dest))
                        src.CopyTo(dst);
                }
            }

            // Il programma da aprire alla fine: lo scrive l'installer; se c'e' la copia non elevata lo apre lei.
            string launch = ArgValue(args, "--launch-file");
            bool ownLaunch = launch == null;
            if (ownLaunch) launch = Path.Combine(temp, "avvio.txt");
            StringBuilder cmd = new StringBuilder();
            cmd.Append("-B ").Append(Quote(Path.Combine(temp, "germano_install.py")));
            cmd.Append(" install --payload ").Append(Quote(exe));
            if (ownLaunch) cmd.Append(' ').Append(Quote("--launch-file=" + launch));
            foreach (string a in args) cmd.Append(' ').Append(Quote(a));
            ProcessStartInfo psi = new ProcessStartInfo(Path.Combine(temp, "runtime", "pythonw.exe"), cmd.ToString());
            psi.UseShellExecute = false;
            psi.WorkingDirectory = temp;
            int code;
            using (Process p = Process.Start(psi))
            {
                p.WaitForExit();
                code = p.ExitCode;
            }
            if (ownLaunch) LaunchFromFile(launch, IsElevated());
            return code;
        }
        catch (InvalidDataException)
        {
            Fail(it ? "L'installer è danneggiato o incompleto.\n\nScaricalo di nuovo da https://download.germano.ai/"
                    : "The installer is damaged or incomplete.\n\nDownload it again from https://download.germano.ai/");
            return 1;
        }
        catch (Exception ex)
        {
            Fail((it ? "Impossibile avviare l'installazione di Germano AI:\n\n" : "Cannot start the Germano AI setup:\n\n")
                 + ex.Message);
            return 1;
        }
        finally
        {
            if (temp != null) Cleanup(temp);
        }
    }

    // Apre il programma scritto dall'installer. Se questo processo e' elevato (installer avviato gia' come
    // amministratore) lo affida a Esplora file, che lo apre con i permessi normali dell'utente.
    static void LaunchFromFile(string file, bool deElevate)
    {
        try
        {
            if (!File.Exists(file)) return;
            string target = File.ReadAllText(file, Encoding.UTF8).Trim();
            if (target.Length == 0 || !File.Exists(target)) return;
            ProcessStartInfo psi;
            if (deElevate)
            {
                psi = new ProcessStartInfo(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Windows), "explorer.exe"),
                                           Quote(target));
                psi.UseShellExecute = false;
            }
            else
            {
                psi = new ProcessStartInfo(target);
                psi.UseShellExecute = true;
            }
            psi.WorkingDirectory = Path.GetDirectoryName(target);
            Process p = Process.Start(psi);
            if (p != null) p.Dispose();
        }
        catch (Exception)
        {
            // Germano resta comunque raggiungibile dal collegamento sul Desktop e dal menu Start
        }
    }

    static bool IsElevated()
    {
        using (WindowsIdentity id = WindowsIdentity.GetCurrent())
            return new WindowsPrincipal(id).IsInRole(WindowsBuiltInRole.Administrator);
    }

    static bool HasArg(string[] args, string name)
    {
        foreach (string a in args) if (a == name) return true;
        return false;
    }

    static string ArgValue(string[] args, string name)
    {
        foreach (string a in args) if (a.StartsWith(name + "=")) return a.Substring(name.Length + 1);
        return null;
    }

    // Cartelle, SID e variabili dell'utente che ha avviato l'installazione (stesse chiavi di germano_install.py).
    static string UserContextJson()
    {
        string[,] folders = {
            { "Documents", "FDD39AD0-238F-46AF-ADB4-6C85480369C7" }, { "Desktop", "B4BFCC3A-DB2C-424C-B029-7FE99A87C641" },
            { "LocalAppData", "F1B32785-6FBA-4FCF-9D55-7B8E7F157091" }, { "UserProgramFiles", "5CD7AEE2-2219-4A67-B85D-6C9CE15660CB" },
            { "Programs", "A77F5D77-2E2B-44C3-A6A2-ABA601054A51" }, { "Profile", "5E6C858F-0E22-4760-9AFE-EA3317B67173" } };
        StringBuilder sb = new StringBuilder("{");
        using (WindowsIdentity id = WindowsIdentity.GetCurrent())
            sb.Append("\"sid\":").Append(Json(id.User.Value));
        sb.Append(",\"folders\":{");
        bool first = true;
        for (int i = 0; i < folders.GetLength(0); i++)
        {
            string path = KnownFolder(folders[i, 1]);
            if (path == null) continue;
            if (!first) sb.Append(',');
            first = false;
            sb.Append(Json(folders[i, 0])).Append(':').Append(Json(path));
        }
        sb.Append("},\"env\":{");
        first = true;
        foreach (string name in new string[] { "OneDrive", "OneDriveCommercial", "OneDriveConsumer" })
        {
            string value = Environment.GetEnvironmentVariable(name);
            if (string.IsNullOrEmpty(value)) continue;
            if (!first) sb.Append(',');
            first = false;
            sb.Append(Json(name)).Append(':').Append(Json(value));
        }
        return sb.Append("}}").ToString();
    }

    [DllImport("shell32.dll")]
    static extern int SHGetKnownFolderPath([MarshalAs(UnmanagedType.LPStruct)] Guid rfid, uint flags, IntPtr token,
                                           out IntPtr path);

    // KF_FLAG_CREATE (come germano_install.py): senza, una cartella che non esiste ancora (es. Programs in un profilo
    // nuovo) non verrebbe restituita e la copia elevata userebbe quella dell'account che ha concesso i permessi.
    static string KnownFolder(string id)
    {
        IntPtr p;
        if (SHGetKnownFolderPath(new Guid(id), 0x8000, IntPtr.Zero, out p) != 0) return null;
        try { return Marshal.PtrToStringUni(p); }
        finally { Marshal.FreeCoTaskMem(p); }
    }

    static string Json(string s)
    {
        StringBuilder sb = new StringBuilder("\"");
        foreach (char c in s)
        {
            if (c == '\\' || c == '"') sb.Append('\\').Append(c);
            else if (c < 0x20) sb.AppendFormat("\\u{0:x4}", (int)c);
            else sb.Append(c);
        }
        return sb.Append('"').ToString();
    }

    // Argomento per la riga di comando di Windows (regole di CommandLineToArgvW).
    static string Quote(string s)
    {
        if (s.Length > 0 && s.IndexOfAny(new char[] { ' ', '\t', '"' }) < 0) return s;
        StringBuilder sb = new StringBuilder("\"");
        int slashes = 0;
        foreach (char c in s)
        {
            if (c == '\\') { slashes++; continue; }
            if (c == '"') { sb.Append('\\', slashes * 2 + 1).Append('"'); slashes = 0; continue; }
            sb.Append('\\', slashes).Append(c);
            slashes = 0;
        }
        sb.Append('\\', slashes * 2).Append('"');
        return sb.ToString();
    }

    // La cartella temporanea si elimina appena l'interprete l'ha liberata.
    static void Cleanup(string dir)
    {
        for (int i = 0; i < 40; i++)
        {
            try
            {
                if (Directory.Exists(dir)) Directory.Delete(dir, true);
                return;
            }
            catch (Exception)
            {
                Thread.Sleep(250);
            }
        }
    }

    static void Fail(string text)
    {
        MessageBox.Show(text, "Germano AI", MessageBoxButtons.OK, MessageBoxIcon.Error);
    }
}
