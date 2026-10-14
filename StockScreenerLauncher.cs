using System;
using System.Diagnostics;
using System.IO;
using System.Text;

internal static class StockScreenerLauncher
{
    private static int Main(string[] args)
    {
        string root = AppDomain.CurrentDomain.BaseDirectory;
        string python = Path.Combine(root, ".venv", "Scripts", "python.exe");
        string script = Path.Combine(root, "main.py");

        if (!File.Exists(python) || !File.Exists(script))
        {
            Console.WriteLine("스크리너 파일 또는 Python 가상환경을 찾을 수 없습니다.");
            Console.WriteLine("PowerShell에서 설치: .\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt");
            WaitForEnter();
            return 2;
        }

        Console.WriteLine("미국주식 스윙 스크리너");
        Console.WriteLine("프로젝트: " + root);
        Console.WriteLine();

        bool showHelp = Array.IndexOf(args, "--help") >= 0 || Array.IndexOf(args, "-h") >= 0;
        if (!showHelp && !EnsureSecUserAgent(root))
        {
            WaitForEnter();
            return 2;
        }

        var start = new ProcessStartInfo();
        start.FileName = python;
        start.WorkingDirectory = root;
        start.UseShellExecute = false;
        start.Arguments = Quote(script);
        foreach (string arg in args) start.Arguments += " " + Quote(arg);

        int exitCode;
        try
        {
            using (Process child = Process.Start(start))
            {
                child.WaitForExit();
                exitCode = child.ExitCode;
            }
        }
        catch (Exception ex)
        {
            Console.WriteLine("스크리너를 시작하지 못했습니다: " + ex.Message);
            exitCode = 1;
        }

        Console.WriteLine();
        Console.WriteLine("프로세스 종료 코드: " + exitCode);
        Console.WriteLine("Enter 키를 누르면 창이 닫힙니다.");
        Console.ReadLine();
        return exitCode;
    }

    private static string Quote(string value)
    {
        var result = new StringBuilder("\"");
        int slashes = 0;
        foreach (char c in value)
        {
            if (c == '\\') { slashes++; continue; }
            if (c == '"')
            {
                result.Append('\\', slashes * 2 + 1).Append('"');
                slashes = 0;
                continue;
            }
            result.Append('\\', slashes).Append(c);
            slashes = 0;
        }
        result.Append('\\', slashes * 2).Append('"');
        return result.ToString();
    }

    private static bool EnsureSecUserAgent(string root)
    {
        string envPath = Path.Combine(root, ".env");
        string current = Environment.GetEnvironmentVariable("SEC_USER_AGENT");
        string[] lines = File.Exists(envPath) ? File.ReadAllLines(envPath) : new string[0];
        foreach (string line in lines)
        {
            string trimmed = line.Trim();
            if (trimmed.StartsWith("SEC_USER_AGENT=", StringComparison.OrdinalIgnoreCase))
                current = trimmed.Substring("SEC_USER_AGENT=".Length).Trim().Trim('"', '\'');
        }
        if (!String.IsNullOrWhiteSpace(current) && current.IndexOf("example.com", StringComparison.OrdinalIgnoreCase) < 0)
            return true;

        Console.WriteLine("SEC 공개 데이터 요청에는 연락 가능한 이메일이 필요합니다.");
        Console.Write("연락 이메일을 입력하세요 (.env 파일에 저장됩니다): ");
        string email = Console.ReadLine();
        if (String.IsNullOrWhiteSpace(email) || !email.Contains("@") || email.IndexOf("example.com", StringComparison.OrdinalIgnoreCase) >= 0)
        {
            Console.WriteLine("SEC 자료를 요청하려면 실제 연락 이메일이 필요합니다.");
            return false;
        }

        var updated = new System.Collections.Generic.List<string>();
        foreach (string line in lines)
            if (!line.TrimStart().StartsWith("SEC_USER_AGENT=", StringComparison.OrdinalIgnoreCase)) updated.Add(line);
        updated.Add("SEC_USER_AGENT=USStockScreener/1.0 " + email.Trim());
        File.WriteAllLines(envPath, updated.ToArray(), new UTF8Encoding(false));
        return true;
    }

    private static void WaitForEnter()
    {
        Console.WriteLine("Enter 키를 누르면 창이 닫힙니다.");
        Console.ReadLine();
    }
}
