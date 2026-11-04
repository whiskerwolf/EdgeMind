using System;
using System.IO;
using System.Net;
using System.Text;
using System.Diagnostics;
using System.Threading;

namespace EdgeMind.NativeHost
{
    class Program
    {
        private static string s_projectRoot;
        private static string s_logFilePath;
        private static readonly object s_logLock = new object();

        static void Main(string[] args)
        {
            // Initialize directories
            try
            {
                string baseDir = AppDomain.CurrentDomain.BaseDirectory;
                // Executable is in <projectRoot>\scripts\
                s_projectRoot = Path.GetFullPath(Path.Combine(baseDir, ".."));
                string logDir = Path.Combine(s_projectRoot, "logs");
                if (!Directory.Exists(logDir))
                {
                    Directory.CreateDirectory(logDir);
                }
                s_logFilePath = Path.Combine(logDir, "edgemind-native-host.log");
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine("Failed to initialize paths: " + ex.Message);
            }

            // Command-line diagnostic test mode (when run manually from terminal)
            if (args.Length > 0 && (args[0] == "--test" || args[0] == "-t" || args[0] == "--check"))
            {
                RunCliTest();
                return;
            }

            Log("EdgeMind Native Host started by Chrome. Args: " + string.Join(" ", args));

            // Standard Chrome Native Messaging stdio loop
            try
            {
                using (Stream stdin = Console.OpenStandardInput())
                using (Stream stdout = Console.OpenStandardOutput())
                using (BinaryReader reader = new BinaryReader(stdin))
                using (BinaryWriter writer = new BinaryWriter(stdout))
                {
                    while (true)
                    {
                        int length = 0;
                        try
                        {
                            length = reader.ReadInt32();
                        }
                        catch (EndOfStreamException)
                        {
                            Log("Standard input closed by Chrome (EOF). Exiting cleanly.");
                            break;
                        }

                        if (length <= 0 || length > 1024 * 1024)
                        {
                            Log("Invalid message length received: " + length + ". Exiting.");
                            break;
                        }

                        byte[] msgBytes = reader.ReadBytes(length);
                        string messageText = Encoding.UTF8.GetString(msgBytes);
                        Log("Received message: " + messageText);

                        string responseJson = HandleMessage(messageText);
                        Log("Sending response: " + responseJson);

                        byte[] respBytes = Encoding.UTF8.GetBytes(responseJson);
                        writer.Write(respBytes.Length);
                        writer.Write(respBytes);
                        writer.Flush();
                    }
                }
            }
            catch (Exception ex)
            {
                Log("Exception in stdio message loop: " + ex.ToString());
            }

            Log("EdgeMind Native Host terminating.");
        }

        private static string HandleMessage(string json)
        {
            string action = "start_backend";
            if (!string.IsNullOrEmpty(json))
            {
                // Simple robust action extraction
                if (json.Contains("\"action\""))
                {
                    int idx = json.IndexOf("\"action\"");
                    int colon = json.IndexOf(':', idx);
                    if (colon > 0)
                    {
                        int quote1 = json.IndexOf('"', colon);
                        if (quote1 > 0)
                        {
                            int quote2 = json.IndexOf('"', quote1 + 1);
                            if (quote2 > quote1)
                            {
                                action = json.Substring(quote1 + 1, quote2 - quote1 - 1).Trim();
                            }
                        }
                    }
                }
            }

            if (action == "ping")
            {
                return FormatJsonResponse("PONG", "EdgeMind Native Host is responsive.", true);
            }
            else if (action == "check_status")
            {
                string detail;
                bool isHealthy = CheckApiHealth(out detail);
                return FormatJsonResponse(
                    isHealthy ? "CONNECTED" : "OFFLINE",
                    detail,
                    isHealthy
                );
            }
            else // default: start_backend
            {
                string detail;
                bool isStarted = EnsureBackendRunning(out detail);
                string status = isStarted ? "CONNECTED" : "ERROR";
                return FormatJsonResponse(status, detail, isStarted);
            }
        }

        public static bool CheckApiHealth(out string detail)
        {
            string url = "http://127.0.0.1:8000/health";
            try
            {
                HttpWebRequest request = (HttpWebRequest)WebRequest.Create(url);
                request.Method = "GET";
                request.Timeout = 2000;
                request.ReadWriteTimeout = 2000;

                using (HttpWebResponse response = (HttpWebResponse)request.GetResponse())
                {
                    if (response.StatusCode == HttpStatusCode.OK)
                    {
                        using (StreamReader sr = new StreamReader(response.GetResponseStream(), Encoding.UTF8))
                        {
                            string body = sr.ReadToEnd();
                            if (body.Contains("\"status\":\"healthy\"") || body.Contains("\"status\": \"healthy\""))
                            {
                                detail = "EdgeMind API is healthy and connected.";
                                return true;
                            }
                        }
                    }
                    detail = "EdgeMind API returned status code " + (int)response.StatusCode;
                    return false;
                }
            }
            catch (WebException webEx)
            {
                detail = "Cannot reach EdgeMind API: " + webEx.Message;
                return false;
            }
            catch (Exception ex)
            {
                detail = "Health check error: " + ex.Message;
                return false;
            }
        }

        public static bool EnsureBackendRunning(out string detail)
        {
            // 1. First check if already healthy
            if (CheckApiHealth(out detail))
            {
                Log("Backend is already running and healthy.");
                detail = "EdgeMind API is already active and healthy.";
                return true;
            }

            Log("Backend is offline. Initiating background startup...");

            // 2. Locate start_edgemind_api.ps1
            string scriptPath = Path.Combine(s_projectRoot, "scripts", "start_edgemind_api.ps1");
            if (!File.Exists(scriptPath))
            {
                detail = "Startup script not found at: " + scriptPath;
                Log("[ERROR] " + detail);
                return false;
            }

            try
            {
                ProcessStartInfo psi = new ProcessStartInfo();
                psi.FileName = "powershell.exe";
                psi.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File \"" + scriptPath + "\"";
                psi.WorkingDirectory = s_projectRoot;
                psi.CreateNoWindow = true;
                psi.UseShellExecute = false;
                psi.WindowStyle = ProcessWindowStyle.Hidden;
                // CRITICAL: Must redirect stdout and stderr so child process text does NOT leak into Chrome's binary pipe!
                psi.RedirectStandardOutput = true;
                psi.RedirectStandardError = true;

                Log("Spawning startup script: powershell.exe " + psi.Arguments);
                using (Process proc = new Process())
                {
                    proc.StartInfo = psi;
                    StringBuilder outSb = new StringBuilder();
                    StringBuilder errSb = new StringBuilder();

                    proc.OutputDataReceived += (s, e) => {
                        if (!string.IsNullOrEmpty(e.Data)) outSb.AppendLine(e.Data);
                    };
                    proc.ErrorDataReceived += (s, e) => {
                        if (!string.IsNullOrEmpty(e.Data)) errSb.AppendLine(e.Data);
                    };

                    proc.Start();
                    proc.BeginOutputReadLine();
                    proc.BeginErrorReadLine();

                    bool exited = proc.WaitForExit(15000);
                    Log("Startup script finished. Exited: " + exited + ", ExitCode: " + (exited ? proc.ExitCode.ToString() : "timed_out"));
                    if (outSb.Length > 0)
                    {
                        Log("Startup script stdout: " + outSb.ToString().Trim().Replace("\r\n", " | ").Replace("\n", " | "));
                    }
                    if (errSb.Length > 0)
                    {
                        Log("Startup script stderr: " + errSb.ToString().Trim().Replace("\r\n", " | ").Replace("\n", " | "));
                    }
                }
            }
            catch (Exception ex)
            {
                detail = "Failed to launch powershell startup script: " + ex.Message;
                Log("[ERROR] " + detail);
                return false;
            }

            // 3. Poll /health for up to 8 seconds to confirm responsiveness
            Stopwatch sw = Stopwatch.StartNew();
            while (sw.ElapsedMilliseconds < 8000)
            {
                Thread.Sleep(300);
                if (CheckApiHealth(out detail))
                {
                    Log("Backend verified healthy after " + sw.ElapsedMilliseconds + " ms.");
                    detail = "EdgeMind API started successfully.";
                    return true;
                }
            }

            // 4. If health check still fails, inspect error log
            string errLogPath = Path.Combine(s_projectRoot, "logs", "edgemind-api-error.log");
            string recentErr = "";
            if (File.Exists(errLogPath))
            {
                try
                {
                    string[] lines = File.ReadAllLines(errLogPath);
                    if (lines.Length > 0)
                    {
                        int start = Math.Max(0, lines.Length - 5);
                        recentErr = string.Join(" | ", lines, start, lines.Length - start);
                    }
                }
                catch { }
            }

            detail = "EdgeMind API failed to respond to /health within timeout. " + recentErr;
            Log("[ERROR] " + detail);
            return false;
        }

        private static string FormatJsonResponse(string status, string message, bool connected)
        {
            StringBuilder sb = new StringBuilder();
            sb.Append("{");
            sb.Append("\"status\":\"").Append(EscapeJson(status)).Append("\",");
            sb.Append("\"service\":\"EdgeMind\",");
            sb.Append("\"connected\":").Append(connected ? "true" : "false").Append(",");
            sb.Append("\"message\":\"").Append(EscapeJson(message)).Append("\",");
            sb.Append("\"endpoint\":\"http://127.0.0.1:8000\",");
            sb.Append("\"timestamp\":\"").Append(DateTime.UtcNow.ToString("o")).Append("\"");
            sb.Append("}");
            return sb.ToString();
        }

        private static string EscapeJson(string s)
        {
            if (string.IsNullOrEmpty(s)) return "";
            StringBuilder sb = new StringBuilder();
            foreach (char c in s)
            {
                switch (c)
                {
                    case '\\': sb.Append("\\\\"); break;
                    case '"': sb.Append("\\\""); break;
                    case '\b': sb.Append("\\b"); break;
                    case '\f': sb.Append("\\f"); break;
                    case '\n': sb.Append("\\n"); break;
                    case '\r': sb.Append("\\r"); break;
                    case '\t': sb.Append("\\t"); break;
                    default:
                        if (c < ' ')
                        {
                            sb.AppendFormat("\\u{0:x4}", (int)c);
                        }
                        else
                        {
                            sb.Append(c);
                        }
                        break;
                }
            }
            return sb.ToString();
        }

        public static void Log(string message)
        {
            string line = string.Format("[{0:yyyy-MM-dd HH:mm:ss.fff}] {1}", DateTime.UtcNow, message);
            try
            {
                Console.Error.WriteLine(line);
                if (!string.IsNullOrEmpty(s_logFilePath))
                {
                    lock (s_logLock)
                    {
                        File.AppendAllText(s_logFilePath, line + Environment.NewLine);
                    }
                }
            }
            catch
            {
                // Never crash because of logging
            }
        }

        private static void RunCliTest()
        {
            Console.WriteLine("=== EdgeMind Native Host CLI Diagnostic Test ===");
            Console.WriteLine("Project Root: " + s_projectRoot);
            Console.WriteLine("Log File:     " + s_logFilePath);

            string detail;
            Console.Write("Checking /health... ");
            bool healthy = CheckApiHealth(out detail);
            Console.WriteLine(healthy ? "ONLINE" : "OFFLINE");
            Console.WriteLine("Detail: " + detail);

            Console.WriteLine("\nTesting EnsureBackendRunning()...");
            bool started = EnsureBackendRunning(out detail);
            Console.WriteLine("Result: " + (started ? "SUCCESS" : "FAILED"));
            Console.WriteLine("Detail: " + detail);

            string jsonResp = FormatJsonResponse(started ? "CONNECTED" : "ERROR", detail, started);
            Console.WriteLine("\nGenerated JSON Protocol Response:\n" + jsonResp);
        }
    }
}
