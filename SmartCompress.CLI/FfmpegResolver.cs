using System.Diagnostics;

namespace SmartCompress;

/// <summary>
/// Locates ffmpeg + ffprobe. Order: $PATH first (typical on Linux/macOS), then
/// bundled in the app's ffmpeg folder, then download.
/// </summary>
public static class FfmpegResolver
{
    public enum Source { Path, Bundled, Downloaded }

    public sealed record Resolved(string Directory, string FfmpegPath, string FfprobePath, Source Source);

    public static Resolved? TryFindOnPath()
    {
        var ffmpegName  = OperatingSystem.IsWindows() ? "ffmpeg.exe"  : "ffmpeg";
        var ffprobeName = OperatingSystem.IsWindows() ? "ffprobe.exe" : "ffprobe";

        var pathEnv = Environment.GetEnvironmentVariable("PATH");
        if (string.IsNullOrEmpty(pathEnv)) return null;

        foreach (var rawDir in pathEnv.Split(Path.PathSeparator))
        {
            var dir = rawDir.Trim().Trim('"');
            if (string.IsNullOrEmpty(dir)) continue;

            string ffmpegPath, ffprobePath;
            try
            {
                ffmpegPath  = Path.Combine(dir, ffmpegName);
                ffprobePath = Path.Combine(dir, ffprobeName);
            }
            catch { continue; }

            // Both binaries must live in the same dir — FFMpegCore points at a
            // single BinaryFolder and looks for both there.
            if (File.Exists(ffmpegPath) && File.Exists(ffprobePath) && IsUsable(ffmpegPath))
                return new Resolved(dir, ffmpegPath, ffprobePath, Source.Path);
        }
        return null;
    }

    private static bool IsUsable(string ffmpegExe)
    {
        try
        {
            var psi = new ProcessStartInfo(ffmpegExe)
            {
                RedirectStandardOutput = true,
                RedirectStandardError  = true,
                UseShellExecute        = false,
                CreateNoWindow         = true,
            };
            psi.ArgumentList.Add("-version");
            using var p = Process.Start(psi);
            if (p == null) return false;
            var output = p.StandardOutput.ReadToEnd();
            if (!p.WaitForExit(3000)) { try { p.Kill(); } catch { } return false; }
            if (p.ExitCode != 0) return false;

            // Need ffmpeg 4.0+ for the flags we use (-progress pipe:1, modern scale options).
            return ParseMajor(output) is int major && major >= 4;
        }
        catch { return false; }
    }

    private static int? ParseMajor(string versionOutput)
    {
        // First line: "ffmpeg version 6.0 ..." or "ffmpeg version n4.4 ..." or "ffmpeg version N-99999-g... ..."
        var line = versionOutput.Split('\n')[0];
        var parts = line.Split(' ', StringSplitOptions.RemoveEmptyEntries);
        if (parts.Length < 3) return null;
        var v = parts[2].TrimStart('n', 'v', 'N');
        var dot = v.IndexOf('.');
        var head = dot >= 0 ? v[..dot] : v;
        // Git-built ffmpeg sometimes reports "N-99999-g..." — accept it as "recent enough".
        if (head.StartsWith("-")) return 99;
        return int.TryParse(head, out var n) ? n : null;
    }
}
