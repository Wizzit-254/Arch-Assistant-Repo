using System;
using System.IO;
using System.Net;
using System.Net.Security;
using System.Diagnostics;
using System.Windows.Forms;
using System.Drawing;
using System.Security.Cryptography.X509Certificates;
using System.IO.Compression;

namespace ArchInstaller
{
    class Program
    {
        static string RepoOwner = "YOUR_GITHUB_USERNAME";
        static string RepoName = "Arch-Assistant-Repo";
        static string InstallDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), "Arch Assistant");
        static string AppZipName = "Arch-Assistant-App.zip";

        [STAThread]
        static void Main()
        {
            ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12 | SecurityProtocolType.Tls11 | SecurityProtocolType.Tls;
            ServicePointManager.ServerCertificateValidationCallback = delegate { return true; };

            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);

            var result = MessageBox.Show(
                "Arch Assistant Installer\n\n" +
                "This will download and install Arch Assistant.\n\n" +
                "Requirements:\n" +
                "  - Python 3.10+\n" +
                "  - Internet connection\n" +
                "  - ~3 GB free disk space\n\n" +
                "Proceed?",
                "Arch Assistant Installer",
                MessageBoxButtons.YesNo, MessageBoxIcon.Question);
            if (result != DialogResult.Yes) return;

            string tempDir = Path.Combine(Path.GetTempPath(), "arch-assistant-setup");
            try { if (Directory.Exists(tempDir)) Directory.Delete(tempDir, true); } catch { }
            Directory.CreateDirectory(tempDir);

            var progress = new ProgressForm();
            progress.Show();

            try
            {
                progress.UpdateStatus("Downloading application...");
                string zipPath = Path.Combine(tempDir, AppZipName);
                string url = "https://github.com/" + RepoOwner + "/" + RepoName + "/releases/latest/download/" + AppZipName;
                DownloadFile(url, zipPath, progress);

                progress.UpdateStatus("Extracting...");
                progress.Refresh();
                string extractDir = Path.Combine(tempDir, "app");
                ZipFile.ExtractToDirectory(zipPath, extractDir);

                progress.UpdateStatus("Installing...");
                progress.Refresh();
                string srcDir = Path.Combine(extractDir, "Arch Assistant");
                if (!Directory.Exists(srcDir))
                {
                    progress.Close();
                    MessageBox.Show("ERROR: Arch Assistant directory not found in download.", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
                    return;
                }
                if (Directory.Exists(InstallDir)) Directory.Delete(InstallDir, true);
                CopyDir(srcDir, InstallDir);

                progress.UpdateStatus("Creating shortcuts...");
                progress.Refresh();
                string desktop = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
                MakeShortcut(Path.Combine(desktop, "Arch Assistant.lnk"), Path.Combine(InstallDir, "Arch.exe"), InstallDir);
                string sm = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
                    @"Microsoft\Windows\Start Menu\Programs\Arch Assistant");
                Directory.CreateDirectory(sm);
                MakeShortcut(Path.Combine(sm, "Arch Assistant.lnk"), Path.Combine(InstallDir, "Arch.exe"), InstallDir);
                MakeShortcut(Path.Combine(sm, "Uninstall.lnk"), Path.Combine(InstallDir, "uninstall.bat"), InstallDir);

                try { Directory.Delete(tempDir, true); } catch { }
                progress.Close();

                var done = MessageBox.Show(
                    "Installed!\n\nLocation: " + InstallDir + "\n\nFirst launch downloads AI models (~2 GB).\nLaunch now?",
                    "Done", MessageBoxButtons.YesNo, MessageBoxIcon.Information);
                if (done == DialogResult.Yes)
                    Process.Start(new ProcessStartInfo { FileName = Path.Combine(InstallDir, "Arch.exe"), WorkingDirectory = InstallDir, UseShellExecute = true });
            }
            catch (Exception ex)
            {
                progress.Close();
                MessageBox.Show("Error: " + ex.Message + "\n\n" + ex.StackTrace, "Installation Failed", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }

        static void DownloadFile(string url, string dest, ProgressForm progress)
        {
            HttpWebRequest request = (HttpWebRequest)WebRequest.Create(url);
            request.AllowAutoRedirect = true;
            request.Timeout = 300000;
            request.ReadWriteTimeout = 300000;

            using (HttpWebResponse response = (HttpWebResponse)request.GetResponse())
            {
                long totalBytes = response.ContentLength;
                using (Stream responseStream = response.GetResponseStream())
                using (FileStream fileStream = File.Create(dest))
                {
                    byte[] buffer = new byte[65536];
                    long downloaded = 0;
                    int bytesRead;
                    while ((bytesRead = responseStream.Read(buffer, 0, buffer.Length)) > 0)
                    {
                        fileStream.Write(buffer, 0, bytesRead);
                        downloaded += bytesRead;
                        if (totalBytes > 0)
                        {
                            double pct = (double)downloaded / totalBytes * 100;
                            string mb = (downloaded / 1048576.0).ToString("F1");
                            string total = (totalBytes / 1048576.0).ToString("F1");
                            progress.UpdateStatus(string.Format("Downloading... {0} / {1} MB ({2}%)", mb, total, (int)pct));
                        }
                        else
                        {
                            string mb = (downloaded / 1048576.0).ToString("F1");
                            progress.UpdateStatus(string.Format("Downloading... {0} MB", mb));
                        }
                        Application.DoEvents();
                    }
                }
            }
        }

        static void CopyDir(string src, string dst)
        {
            Directory.CreateDirectory(dst);
            foreach (string f in Directory.GetFiles(src))
                File.Copy(f, Path.Combine(dst, Path.GetFileName(f)), true);
            foreach (string d in Directory.GetDirectories(src))
                CopyDir(d, Path.Combine(dst, Path.GetFileName(d)));
        }

        static void MakeShortcut(string path, string target, string workDir)
        {
            dynamic shell = Activator.CreateInstance(Type.GetTypeFromProgID("WScript.Shell"));
            dynamic sc = shell.CreateShortcut(path);
            sc.TargetPath = target;
            sc.WorkingDirectory = workDir;
            sc.Description = "Arch AI Assistant";
            sc.Save();
        }
    }

    class ProgressForm : Form
    {
        private Label lbl;
        public ProgressForm()
        {
            Text = "Arch Assistant Installer";
            Size = new Size(420, 130);
            StartPosition = FormStartPosition.CenterScreen;
            FormBorderStyle = FormBorderStyle.FixedDialog;
            MaximizeBox = false; MinimizeBox = false; ControlBox = false;
            lbl = new Label { Text = "Starting...", Location = new Point(20, 15), Size = new Size(380, 30), Font = new Font("Segoe UI", 11) };
            Controls.Add(lbl);
            Controls.Add(new ProgressBar { Style = ProgressBarStyle.Marquee, Location = new Point(20, 55), Size = new Size(380, 30), MarqueeAnimationSpeed = 30 });
        }
        public void UpdateStatus(string t) { lbl.Text = t; Refresh(); }
    }
}
