// Germano AI - avviatore dell'installer in un solo file (germano-<versione>.exe, germano-client-<versione>.exe).
//
// Compilato da costruisci_installer_windows.py con il compilatore C# di .NET Framework 4, gia' presente in ogni
// Windows 10/11 (nessun SDK da installare). In coda all'eseguibile ci sono:
//   1. il "kit": un archivio ZIP con l'interprete Python minimo e germano_install.py (l'installer vero e proprio);
//   2. l'archivio ZIP con tutti i file del programma (runtime, modelli IA, interfaccia);
//   3. una coda di 48 byte: firma "GERMANO.SFX.0001" e posizione/lunghezza (64 bit) del kit e dell'archivio.
// L'avviatore estrae solo il kit in una cartella temporanea, avvia l'installer passandogli il percorso di questo
// .exe (da cui l'installer legge direttamente l'archivio, senza copie intermedie), attende la fine, elimina la
// cartella temporanea e restituisce lo stesso codice di uscita (0 riuscito, 1 errore, 2 annullato).
using System;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.IO.Compression;
using System.Reflection;
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

    [STAThread]
    static int Main(string[] args)
    {
        Application.EnableVisualStyles();
        bool it = CultureInfo.CurrentUICulture.TwoLetterISOLanguageName == "it";
        string temp = null;
        try
        {
            if (!Environment.Is64BitOperatingSystem)
            {
                Fail(it ? "Germano AI richiede Windows 10 o 11 a 64 bit." : "Germano AI requires 64-bit Windows 10 or 11.");
                return 1;
            }
            string exe = Assembly.GetExecutingAssembly().Location;
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

            StringBuilder cmd = new StringBuilder();
            cmd.Append("-B ").Append(Quote(Path.Combine(temp, "germano_install.py")));
            cmd.Append(" install --payload ").Append(Quote(exe));
            foreach (string a in args) cmd.Append(' ').Append(Quote(a));
            ProcessStartInfo psi = new ProcessStartInfo(Path.Combine(temp, "runtime", "pythonw.exe"), cmd.ToString());
            psi.UseShellExecute = false;
            psi.WorkingDirectory = temp;
            using (Process p = Process.Start(psi))
            {
                p.WaitForExit();
                return p.ExitCode;
            }
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
