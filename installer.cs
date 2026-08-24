using System;
using System.IO;
using System.Net;
using System.Net.Security;
using System.Diagnostics;
using System.Windows.Forms;
using System.Drawing;
using System.IO.Compression;

namespace ArchInstaller
{
    class Program
    {
        static string RepoOwner = "Wizzit-254";
        static string RepoName = "Arch-Assistant-Repo";
        static string AppZipName = "Arch-Assistant-App.zip";
        static string InstallDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), "Arch Assistant");

        [STAThread]
        static void Main()
        {
            ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12 | SecurityProtocolType.Tls11 | SecurityProtocolType.Tls;
            ServicePointManager.ServerCertificateValidationCallback = delegate { return true; };
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);

            string downloadUrl = "https://github.com/" + RepoOwner + "/" + RepoName
                + "/releases/latest/download/" + AppZipName;

            DialogResult ask = MessageBox.Show(
                "Arch Assistant Installer\n\n"
                + "This will download and install Arch Assistant.\n\n"
                + "Requirements:\n"
                + "  - Python 3.10 or newer\n"
                + "  - Internet connection\n"
                + "  - ~3 GB free disk space\n\n"
                + "Install to:\n  " + InstallDir + "\n\n"
                + "Proceed?",
                "Arch Assistant Installer",
                MessageBoxButtons.YesNo, MessageBoxIcon.Question);
            if (ask != DialogResult.Yes) return;

            string tempDir = Path.Combine(Path.GetTempPath(), "arch-assistant-setup");
            try { if (Directory.Exists(tempDir)) Directory.Delete(tempDir, true); } catch { }
            Directory.CreateDirectory(tempDir);
            string zipPath = Path.Combine(tempDir, AppZipName);

            var ui = new ProgressForm();
            ui.Show();

            try
            {
                ui.UpdateStatus("Connecting to GitHub...");
                ui.Refresh();

                HttpWebRequest req = (HttpWebRequest)WebRequest.Create(downloadUrl);
                req.AllowAutoRedirect = true;
                req.Timeout = 600000;
                req.ReadWriteTimeout = 600000;
                req.UserAgent = "ArchAssistant-Installer/1.0";

                HttpWebResponse resp;
                try
                {
                    resp = (HttpWebResponse)req.GetResponse();
                }
                catch (WebException wex)
                {
                    ui.Close();
                    string msg = "Could not download the application.\n\n";
                    if (wex.Response != null)
                    {
                        int code = (int)((HttpWebResponse)wex.Response).StatusCode;
                        msg += "Server returned: " + code + "\n\n";
                        if (code == 404)
                        {
                            msg += "The release file was not found.\n"
                                + "Make sure you have published a GitHub release\n"
                                + "with the file '" + AppZipName + "'.\n\n"
                                + "URL:\n" + downloadUrl;
                        }
                        else
                        {
                            msg += wex.Message;
                        }
                    }
                    else
                    {
                        msg += "No internet connection or server unreachable.\n\n" + wex.Message;
                    }
                    MessageBox.Show(msg, "Download Failed", MessageBoxButtons.OK, MessageBoxIcon.Error);
                    return;
                }

                long totalBytes = resp.ContentLength;
                using (Stream rs = resp.GetResponseStream())
                using (FileStream fs = File.Create(zipPath))
                {
                    byte[] buf = new byte[65536];
                    long got = 0;
                    int n;
                    while ((n = rs.Read(buf, 0, buf.Length)) > 0)
                    {
                        fs.Write(buf, 0, n);
                        got += n;
                        if (totalBytes > 0)
                        {
                            double pct = (double)got / totalBytes * 100;
                            ui.UpdateStatus(string.Format("Downloading... {0:N0} / {1:N0} MB ({2}%)",
                                got / 1048576, totalBytes / 1048576, (int)pct));
                        }
                        else
                        {
                            ui.UpdateStatus(string.Format("Downloading... {0:N0} MB", got / 1048576));
                        }
                        Application.DoEvents();
                    }
                }
                resp.Close();

                ui.UpdateStatus("Extracting files...");
                ui.Refresh();
                string extractDir = Path.Combine(tempDir, "app");
                ZipFile.ExtractToDirectory(zipPath, extractDir);

                string srcDir = Path.Combine(extractDir, "Arch Assistant");
                if (!Directory.Exists(srcDir))
                {
                    ui.Close();
                    MessageBox.Show("Archive did not contain 'Arch Assistant' folder.", "Error",
                        MessageBoxButtons.OK, MessageBoxIcon.Error);
                    return;
                }

                ui.UpdateStatus("Installing...");
                ui.Refresh();
                try
                {
                    if (Directory.Exists(InstallDir)) Directory.Delete(InstallDir, true);
                }
                catch (UnauthorizedAccessException)
                {
                    ui.Close();
                    MessageBox.Show("Please right-click the installer and select\n'Run as administrator'.",
                        "Permission Required", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                    return;
                }
                CopyDir(srcDir, InstallDir);

                ui.UpdateStatus("Creating shortcuts...");
                ui.Refresh();
                try
                {
                    string desktop = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
                    MakeShortcut(Path.Combine(desktop, "Arch Assistant.lnk"),
                        Path.Combine(InstallDir, "Arch.exe"), InstallDir);

                    string smDir = Path.Combine(
                        Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
                        @"Microsoft\Windows\Start Menu\Programs\Arch Assistant");
                    Directory.CreateDirectory(smDir);
                    MakeShortcut(Path.Combine(smDir, "Arch Assistant.lnk"),
                        Path.Combine(InstallDir, "Arch.exe"), InstallDir);
                    MakeShortcut(Path.Combine(smDir, "Uninstall.lnk"),
                        Path.Combine(InstallDir, "uninstall.bat"), InstallDir);
                }
                catch { }

                try { Directory.Delete(tempDir, true); } catch { }
                ui.Close();

                DialogResult launch = MessageBox.Show(
                    "Installation complete!\n\n"
                    + "Installed to: " + InstallDir + "\n\n"
                    + "First launch will download AI models (~2 GB).\n"
                    + "This happens automatically in the background.\n\n"
                    + "Launch Arch Assistant now?",
                    "Arch Assistant", MessageBoxButtons.YesNo, MessageBoxIcon.Information);
                if (launch == DialogResult.Yes)
                {
                    Process.Start(new ProcessStartInfo
                    {
                        FileName = Path.Combine(InstallDir, "Arch.exe"),
                        WorkingDirectory = InstallDir,
                        UseShellExecute = true
                    });
                }
            }
            catch (Exception ex)
            {
                ui.Close();
                MessageBox.Show("Unexpected error:\n\n" + ex.Message + "\n\n" + ex.StackTrace,
                    "Installation Failed", MessageBoxButtons.OK, MessageBoxIcon.Error);
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
            object sh = Activator.CreateInstance(Type.GetTypeFromProgID("WScript.Shell"));
            dynamic sc = sh.GetType().InvokeMember("CreateShortcut",
                System.Reflection.BindingFlags.InvokeMethod, null, sh, new object[] { path });
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
            Size = new Size(440, 130);
            StartPosition = FormStartPosition.CenterScreen;
            FormBorderStyle = FormBorderStyle.FixedDialog;
            MaximizeBox = false;
            MinimizeBox = false;
            ControlBox = false;
            lbl = new Label
            {
                Text = "Starting...",
                Location = new Point(20, 15),
                Size = new Size(400, 30),
                Font = new Font("Segoe UI", 11)
            };
            Controls.Add(lbl);
            Controls.Add(new ProgressBar
            {
                Style = ProgressBarStyle.Marquee,
                Location = new Point(20, 55),
                Size = new Size(400, 30),
                MarqueeAnimationSpeed = 30
            });
        }
        public void UpdateStatus(string t) { lbl.Text = t; Refresh(); }
    }
}
