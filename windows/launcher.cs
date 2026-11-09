// Compiled locally by setup. Keep stdio and arguments intact for Codex app-server.
using System;
using System.Diagnostics;
using System.Text;

class ArgonLauncher
{
    const string Python = __ARGON_PYTHON__;
    const string Runtime = __ARGON_RUNTIME__;

    static string Quote(string value)
    {
        var result = new StringBuilder("\"");
        int slashes = 0;
        foreach (char ch in value)
        {
            if (ch == '\\') { slashes++; continue; }
            result.Append('\\', ch == '"' ? slashes * 2 + 1 : slashes);
            result.Append(ch);
            slashes = 0;
        }
        result.Append('\\', slashes * 2);
        return result.Append('"').ToString();
    }

    static int Main(string[] args)
    {
        try
        {
            var arguments = new StringBuilder(Quote(Runtime) + " codex");
            foreach (string arg in args) arguments.Append(" " + Quote(arg));
            var info = new ProcessStartInfo(Python, arguments.ToString());
            info.UseShellExecute = false;
            using (var process = Process.Start(info))
            {
                process.WaitForExit();
                return process.ExitCode;
            }
        }
        catch (Exception error)
        {
            Console.Error.WriteLine("Argon launcher: " + error.Message);
            return 1;
        }
    }
}
