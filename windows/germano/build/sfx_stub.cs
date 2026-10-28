// Germano AI - avviatore dell'installer in un solo file (germano-<versione>.exe, germano-client-<versione>.exe).
//
// Compilato da costruisci_installer_windows.py con il compilatore C# di .NET Framework 4, gia' presente in ogni
// Windows 10/11 e Windows Server 2019 o successivo (nessun SDK da installare; sintassi C# 5). In coda all'eseguibile
// ci sono:
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
// La copia elevata e' un piccolo avviatore (i primi byte di questo stesso file, senza kit e archivio) scritto nella
// cartella di lavoro: Windows, prima della richiesta UAC, verifica il file leggendolo tutto, e per 3 GB servivano
// decine di secondi senza che comparisse nulla. L'avviatore elevato legge kit e archivio dall'installer (--source).
//
// L'avviatore estrae solo il kit in una cartella temporanea, avvia l'installer passandogli il percorso di questo
// .exe (da cui l'installer legge direttamente l'archivio, senza copie intermedie), attende la fine, apre il programma
// indicato dall'installer (--launch-file), elimina la cartella temporanea e restituisce lo stesso codice di uscita
// (0 riuscito, 1 errore, 2 annullato).
//
// Schermata di avvio (SetupSplash): compare appena l'avviatore parte, prima della richiesta UAC (Windows puo' impiegare
// alcuni secondi a verificare un file cosi' grande), e resta durante l'estrazione del kit e l'avvio dell'interprete;
// si chiude da sola quando compare la finestra dell'installazione. Non con --silent; nella copia elevata no (la mostra
// gia' la copia che l'ha avviata).
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
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
    const string Product = "@PRODUCT@";
    // suite: true (regola del firewall per la rete locale); client: false (non serve nessun permesso speciale)
    static readonly bool ElevateForInstall = @ELEVATE@;

    [DllImport("user32.dll")]
    static extern bool SetProcessDPIAware();

    [DllImport("user32.dll")]
    static extern bool AllowSetForegroundWindow(int pid);

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    struct OsVersionInfoEx
    {
        public int Size, Major, Minor, Build, Platform;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 128)] public string CsdVersion;
        public ushort SpMajor, SpMinor, SuiteMask;
        public byte ProductType, Reserved;
    }

    [DllImport("ntdll.dll")]
    static extern int RtlGetVersion(ref OsVersionInfoEx info);

    // Versione VERA di Windows: senza manifest di compatibilita' Environment.OSVersion riporta 6.2 anche su Windows
    // 10/11 e Windows Server 2019/2022/2025 (tutti NT 10.0). In caso di dubbio non si blocca nulla.
    static int WindowsMajor()
    {
        OsVersionInfoEx v = new OsVersionInfoEx();
        v.Size = Marshal.SizeOf(typeof(OsVersionInfoEx));
        try { return RtlGetVersion(ref v) == 0 ? v.Major : 10; }
        catch (Exception) { return 10; }
    }

    [STAThread]
    static int Main(string[] args)
    {
        try { SetProcessDPIAware(); } catch (Exception) { }     // testo nitido anche con lo schermo ingrandito
        Application.EnableVisualStyles();
        bool it = CultureInfo.CurrentUICulture.TwoLetterISOLanguageName == "it";
        if (!Environment.Is64BitOperatingSystem || WindowsMajor() < 10)
        {
            Fail(it ? "Germano AI richiede Windows 10, Windows 11 o Windows Server 2019 o superiori a 64 bit."
                    : "Germano AI requires 64-bit Windows 10, Windows 11 or Windows Server 2019 or higher.");
            return 1;
        }
        string exe = Assembly.GetExecutingAssembly().Location;
        bool child = HasArg(args, "--elevated");
        // copia elevata avviata come piccolo avviatore: kit e archivio sono nell'installer originale (--source)
        string source = child ? ArgValue(args, "--source") : null;
        if (source != null && File.Exists(source)) exe = source;
        bool update = HasArg(args, "--update");
        bool noElevation = Environment.GetEnvironmentVariable("GERMANO_SETUP_NO_ELEVATION") == "1";
        if (!child && !HasArg(args, "--silent"))
            SetupSplash.Start(Product, it ? "Avvio dell'installazione in corso..." : "Starting installer...", exe);
        try
        {
            if (ElevateForInstall && !child && !update && !noElevation && !IsElevated())
                return RunElevated(exe, args, it);
            return RunInstaller(exe, args, it);
        }
        finally
        {
            SetupSplash.Stop();
        }
    }

    // Diritto di portare in primo piano la propria finestra, passato al processo avviato (questo processo ha in
    // primo piano la schermata di avvio): la finestra dell'installazione compare davanti, non dietro.
    static void AllowForeground(Process p)
    {
        try { AllowSetForegroundWindow(p.Id); } catch (Exception) { }
    }

    // Copia non elevata: chiede subito i permessi, attende la copia elevata e alla fine apre Germano.
    // Prima di mostrare la richiesta UAC Windows verifica il file da avviare leggendolo tutto: per l'installer della
    // suite (circa 3 GB, non firmato) servono decine di secondi in cui non compare nulla. I permessi si chiedono quindi
    // per un piccolo avviatore: questo stesso programma senza i dati in coda (pochi KB, stessa icona e stesso nome),
    // copiato nella cartella di lavoro, che legge kit e archivio dall'installer originale (--source). Se non si puo'
    // avviare (es. criteri del computer), si chiedono i permessi per l'installer intero, come prima.
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
            string helper = SmallLauncher(exe, work);
            string[] targets = helper != null ? new string[] { helper, exe } : new string[] { exe };
            Process p = null;
            // la schermata di avvio e' gia' visibile (e in primo piano) mentre Windows verifica il file e chiede i permessi
            SetupSplash.WaitReady(1500);
            foreach (string target in targets)
            {
                string arguments = (target == helper ? Quote("--source=" + exe) + " " : "") + cmd.ToString();
                ProcessStartInfo psi = new ProcessStartInfo(target, arguments);
                psi.UseShellExecute = true;
                psi.Verb = "runas";
                psi.WorkingDirectory = Path.GetDirectoryName(exe);
                try
                {
                    p = Process.Start(psi);
                    break;
                }
                catch (Win32Exception ex)
                {
                    if (ex.NativeErrorCode == 1223)           // 1223 = richiesta UAC rifiutata
                    {
                        SetupSplash.Stop();
                        MessageBox.Show(it
                            ? "Per installare Germano AI servono i permessi di amministratore: servono a consentire l'accesso dalla rete locale (regola del firewall di Windows).\n\nAvvia di nuovo l'installer e scegli «Sì»."
                            : "Installing Germano AI requires administrator permission: it is needed to allow access from the local network (Windows Firewall rule).\n\nStart the installer again and choose \"Yes\".",
                            "Germano AI", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                        return 2;
                    }
                    if (target == exe) throw;
                    // il piccolo avviatore non parte: si riprova con l'installer intero
                }
            }
            if (p == null) return 1;
            using (p)
            {
                SetupSplash.Status(it ? "Preparazione dell'installazione..." : "Preparing the installer...");
                SetupSplash.Arm();
                AllowForeground(p);
                p.WaitForExit();
                SetupSplash.Stop();
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
                long kitOff, kitLen;
                if (!ReadTrailer(fs, out kitOff, out kitLen)) throw new InvalidDataException();
                fs.Seek(kitOff, SeekOrigin.Begin);
                kit = new BinaryReader(fs).ReadBytes((int)kitLen);
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
            foreach (string a in args)
                if (!a.StartsWith("--source=")) cmd.Append(' ').Append(Quote(a));   // l'archivio e' gia' in --payload
            ProcessStartInfo psi = new ProcessStartInfo(Path.Combine(temp, "runtime", "pythonw.exe"), cmd.ToString());
            psi.UseShellExecute = false;
            psi.WorkingDirectory = temp;
            int code;
            // la schermata deve aver preso nota delle finestre gia' aperte prima che compaia quella dell'installazione
            SetupSplash.WaitReady(1500);
            using (Process p = Process.Start(psi))
            {
                SetupSplash.Arm();
                AllowForeground(p);
                p.WaitForExit();
                code = p.ExitCode;
            }
            SetupSplash.Stop();
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

    // Coda di 48 byte in fondo al file: posizione e lunghezza del kit (e controllo di quelle dell'archivio).
    static bool ReadTrailer(FileStream fs, out long kitOff, out long kitLen)
    {
        kitOff = kitLen = 0;
        if (fs.Length < TrailerSize) return false;
        fs.Seek(-TrailerSize, SeekOrigin.End);
        BinaryReader br = new BinaryReader(fs);
        string magic = Encoding.ASCII.GetString(br.ReadBytes(16));
        kitOff = br.ReadInt64();
        kitLen = br.ReadInt64();
        long payOff = br.ReadInt64(), payLen = br.ReadInt64();
        long end = fs.Length - TrailerSize;
        return magic == Magic && kitOff > 0 && kitLen > 0 && kitLen <= int.MaxValue && kitOff + kitLen <= end
               && payOff > 0 && payLen > 0 && payOff + payLen <= end;
    }

    // Il piccolo avviatore per la richiesta UAC: i primi byte dell'installer, cioe' il programma compilato senza kit e
    // archivio (il kit comincia subito dopo). null se non si puo' preparare (si usa allora l'installer intero).
    static string SmallLauncher(string exe, string work)
    {
        try
        {
            using (FileStream fs = new FileStream(exe, FileMode.Open, FileAccess.Read, FileShare.Read))
            {
                long kitOff, kitLen;
                if (!ReadTrailer(fs, out kitOff, out kitLen) || kitOff > (8 << 20)) return null;
                fs.Seek(0, SeekOrigin.Begin);
                byte[] stub = new BinaryReader(fs).ReadBytes((int)kitOff);
                if (stub.Length != kitOff || stub[0] != (byte)'M' || stub[1] != (byte)'Z') return null;
                string helper = Path.Combine(work, Path.GetFileName(exe));
                File.WriteAllBytes(helper, stub);
                return helper;
            }
        }
        catch (Exception)
        {
            return null;
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
        SetupSplash.Stop();             // il messaggio non deve restare sotto la schermata di avvio
        MessageBox.Show(text, "Germano AI", MessageBoxButtons.OK, MessageBoxIcon.Error);
    }
}

// Schermata di avvio: finestra nativa (WinForms) in un thread suo, con la propria coda di messaggi, cosi' resta viva e
// animata anche mentre il thread principale aspetta la richiesta UAC o l'installer. Il thread principale non la tocca
// mai direttamente: imposta solo dei campi che lei legge col suo timer (nessuna chiamata tra thread, nessun blocco).
// Si chiude quando compare una NUOVA finestra di dialogo (classe #32770) con «Germano AI» nel titolo di un altro processo
// (la finestra dell'installazione, o un messaggio di errore), quando il thread principale lo chiede, oppure, per
// sicurezza, 2 minuti dopo l'avvio dell'installer se la finestra non e' stata riconosciuta.
sealed class SetupSplash : Form
{
    delegate bool EnumWindowsProc(IntPtr hwnd, IntPtr lParam);

    [DllImport("user32.dll")]
    static extern bool EnumWindows(EnumWindowsProc proc, IntPtr lParam);

    [DllImport("user32.dll")]
    static extern bool IsWindowVisible(IntPtr hwnd);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    static extern int GetClassName(IntPtr hwnd, StringBuilder name, int max);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    static extern int GetWindowText(IntPtr hwnd, StringBuilder text, int max);

    [DllImport("user32.dll")]
    static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint pid);

    [DllImport("user32.dll")]
    static extern bool SetForegroundWindow(IntPtr hwnd);

    [DllImport("user32.dll")]
    static extern bool AllowSetForegroundWindow(int pid);

    [DllImport("user32.dll")]
    static extern bool DestroyIcon(IntPtr icon);

    [DllImport("dwmapi.dll")]
    static extern int DwmSetWindowAttribute(IntPtr hwnd, int attribute, ref int value, int size);

    [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
    static extern int SHDefExtractIcon(string file, int index, uint flags, out IntPtr large, out IntPtr small, uint size);

    const int SafetyMs = 120000;                 // limite dopo l'avvio dell'installer
    static Thread thread;
    static readonly ManualResetEvent ready = new ManualResetEvent(false);
    static volatile bool closeRequested;
    static volatile string statusText;
    static volatile int armedAt;                 // Environment.TickCount all'avvio dell'installer (0 = non ancora)

    readonly string title;
    readonly float scale;
    readonly Font titleFont, textFont;
    readonly Bitmap logo;
    readonly System.Windows.Forms.Timer tick = new System.Windows.Forms.Timer();
    readonly HashSet<IntPtr> before = new HashSet<IntPtr>();
    readonly uint ownPid = (uint)Process.GetCurrentProcess().Id;
    string shownStatus;
    int barPos, frames;

    public static void Start(string product, string status, string exe)
    {
        statusText = status;
        try
        {
            thread = new Thread(delegate ()
            {
                try
                {
                    // un errore della schermata non deve mai mostrare finestre di WinForms: si chiude e basta
                    Application.ThreadException += delegate (object sender, ThreadExceptionEventArgs e) { closeRequested = true; };
                    if (!closeRequested) Application.Run(new SetupSplash(product, status, exe));
                }
                catch (Exception)
                {
                    // senza schermata l'installazione procede come prima
                }
                finally
                {
                    ready.Set();
                }
            });
            thread.SetApartmentState(ApartmentState.STA);
            thread.IsBackground = true;
            thread.Start();
        }
        catch (Exception)
        {
            thread = null;
            ready.Set();
        }
    }

    public static void WaitReady(int ms)
    {
        if (thread != null) ready.WaitOne(ms);
    }

    public static void Status(string text)
    {
        statusText = text;
    }

    public static void Arm()
    {
        int now = Environment.TickCount;
        armedAt = now == 0 ? 1 : now;
    }

    public static void Stop()
    {
        closeRequested = true;
        Thread t = thread;
        if (t != null && t != Thread.CurrentThread && t.IsAlive) t.Join(3000);
    }

    SetupSplash(string product, string status, string exe)
    {
        title = product;
        shownStatus = status;
        using (Graphics g = Graphics.FromHwnd(IntPtr.Zero)) scale = g.DpiX / 96f;
        FormBorderStyle = FormBorderStyle.None;
        StartPosition = FormStartPosition.CenterScreen;
        ShowInTaskbar = true;
        TopMost = true;
        Text = product;
        BackColor = Color.FromArgb(0x0f, 0x17, 0x2a);
        ForeColor = Color.FromArgb(0xf8, 0xfa, 0xfc);
        ClientSize = new Size(S(440), S(150));
        SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.UserPaint, true);
        titleFont = new Font("Segoe UI Semibold", 15f);
        textFont = new Font("Segoe UI", 10f);
        try { Icon = Icon.ExtractAssociatedIcon(exe); } catch (Exception) { }
        logo = LoadLogo(exe, S(44));
        tick.Interval = 16;
        tick.Tick += OnTick;
    }

    int S(int value)
    {
        return (int)Math.Round(value * scale);
    }

    protected override CreateParams CreateParams
    {
        get
        {
            CreateParams cp = base.CreateParams;
            cp.ClassStyle |= 0x20000;            // CS_DROPSHADOW: ombra anche senza bordo
            return cp;
        }
    }

    protected override void OnHandleCreated(EventArgs e)
    {
        base.OnHandleCreated(e);
        try
        {
            int round = 2;                       // Windows 11: angoli arrotondati (DWMWA_WINDOW_CORNER_PREFERENCE)
            DwmSetWindowAttribute(Handle, 33, ref round, 4);
        }
        catch (Exception) { }
    }

    protected override void OnShown(EventArgs e)
    {
        base.OnShown(e);
        foreach (IntPtr h in InstallerWindows()) before.Add(h);   // finestre gia' aperte: non contano
        tick.Start();
        ready.Set();
    }

    protected override void OnFormClosed(FormClosedEventArgs e)
    {
        tick.Stop();
        tick.Dispose();
        titleFont.Dispose();
        textFont.Dispose();
        if (logo != null) logo.Dispose();
        base.OnFormClosed(e);
    }

    static Bitmap LoadLogo(string exe, int size)
    {
        IntPtr large = IntPtr.Zero, small = IntPtr.Zero;
        try
        {
            if (SHDefExtractIcon(exe, 0, 0, out large, out small, (uint)((16 << 16) | (size & 0xffff))) != 0
                || large == IntPtr.Zero) return null;
            using (Icon icon = Icon.FromHandle(large)) return icon.ToBitmap();
        }
        catch (Exception)
        {
            return null;
        }
        finally
        {
            if (large != IntPtr.Zero) DestroyIcon(large);
            if (small != IntPtr.Zero) DestroyIcon(small);
        }
    }

    // Finestre di dialogo visibili di altri processi con «Germano AI» nel titolo (TaskDialog dell'installer, messaggi)
    List<IntPtr> InstallerWindows()
    {
        List<IntPtr> found = new List<IntPtr>();
        StringBuilder buf = new StringBuilder(256);
        EnumWindows(delegate (IntPtr h, IntPtr l)
        {
            uint pid;
            if (!IsWindowVisible(h)) return true;
            GetWindowThreadProcessId(h, out pid);
            if (pid == ownPid) return true;
            buf.Length = 0;
            if (GetClassName(h, buf, buf.Capacity) == 0 || buf.ToString() != "#32770") return true;
            buf.Length = 0;
            if (GetWindowText(h, buf, buf.Capacity) > 0 && buf.ToString().IndexOf("Germano AI", StringComparison.Ordinal) >= 0)
                found.Add(h);
            return true;
        }, IntPtr.Zero);
        return found;
    }

    Rectangle BarRect()
    {
        int pad = S(28);
        return new Rectangle(pad, ClientSize.Height - S(34), ClientSize.Width - 2 * pad, Math.Max(3, S(4)));
    }

    void OnTick(object sender, EventArgs e)
    {
        try
        {
            Step();
        }
        catch (Exception)
        {
            Finish(IntPtr.Zero);
        }
    }

    void Step()
    {
        if (closeRequested) { Finish(IntPtr.Zero); return; }
        Rectangle track = BarRect();
        barPos += Math.Max(2, S(4));
        if (barPos > track.Width + S(110)) barPos = 0;
        Invalidate(track);
        string status = statusText;
        if (status != null && status != shownStatus)
        {
            shownStatus = status;
            Invalidate();
        }
        if (++frames % 6 != 0) return;           // ricerca della finestra dell'installazione ogni ~100 ms
        int armed = armedAt;
        if (armed != 0 && unchecked(Environment.TickCount - armed) > SafetyMs) { Finish(IntPtr.Zero); return; }
        foreach (IntPtr h in InstallerWindows())
        {
            if (before.Contains(h)) continue;
            Finish(h);
            return;
        }
    }

    void Finish(IntPtr installer)
    {
        if (IsDisposed) return;
        tick.Stop();
        if (installer != IntPtr.Zero)
        {
            // questa schermata e' in primo piano: lo passa alla finestra dell'installazione prima di chiudersi
            try
            {
                AllowSetForegroundWindow(-1);
                SetForegroundWindow(installer);
            }
            catch (Exception) { }
        }
        Close();
    }

    protected override void OnPaint(PaintEventArgs e)
    {
        try
        {
            Draw(e.Graphics);
        }
        catch (Exception)
        {
            closeRequested = true;               // il timer chiude la schermata
        }
    }

    void Draw(Graphics g)
    {
        int pad = S(28);
        using (Pen border = new Pen(Color.FromArgb(0x33, 0x41, 0x55)))
            g.DrawRectangle(border, 0, 0, ClientSize.Width - 1, ClientSize.Height - 1);
        int x = pad;
        if (logo != null)
        {
            g.InterpolationMode = InterpolationMode.HighQualityBicubic;
            g.DrawImage(logo, new Rectangle(pad, S(28), S(44), S(44)));
            x = pad + S(44) + S(16);
        }
        TextRenderer.DrawText(g, title, titleFont, new Point(x, S(24)), ForeColor, TextFormatFlags.NoPadding);
        TextRenderer.DrawText(g, shownStatus ?? "", textFont, new Rectangle(x, S(60), ClientSize.Width - x - pad, S(24)),
                              Color.FromArgb(0xcb, 0xd5, 0xe1), TextFormatFlags.NoPadding | TextFormatFlags.EndEllipsis);
        Rectangle track = BarRect();
        using (SolidBrush back = new SolidBrush(Color.FromArgb(0x1e, 0x29, 0x3b)))
            g.FillRectangle(back, track);
        int seg = S(110);
        Rectangle moving = new Rectangle(track.X + barPos - seg, track.Y, seg, track.Height);
        Rectangle part = Rectangle.Intersect(moving, track);
        if (part.Width > 0)
        {
            using (LinearGradientBrush bar = new LinearGradientBrush(moving, Color.FromArgb(0x3b, 0x82, 0xf6),
                                                                     Color.FromArgb(0x8b, 0x5c, 0xf6), LinearGradientMode.Horizontal))
                g.FillRectangle(bar, part);
        }
    }
}
