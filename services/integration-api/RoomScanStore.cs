using System.Text.Json;
using System.Text.RegularExpressions;

public sealed class RoomScanStore
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);
    private readonly string _rootDirectory;

    public RoomScanStore(IConfiguration configuration)
    {
        _rootDirectory = configuration["RoomScans:DataDirectory"]
            ?? Environment.GetEnvironmentVariable("ROOM_SCAN_DATA_DIR")
            ?? Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "DigitalTwin3D",
                "room-scans");
    }

    public async Task SaveAsync(RoomScanRecord scan, CancellationToken cancellationToken)
    {
        EnsureSafeId(scan.RoomId);
        var scanDirectory = Path.Combine(_rootDirectory, scan.RoomId, "scans");
        Directory.CreateDirectory(scanDirectory);

        var json = JsonSerializer.Serialize(scan, JsonOptions);
        var versionPath = Path.Combine(scanDirectory, $"{scan.ScanId}.json");
        var latestPath = Path.Combine(scanDirectory, "latest.json");
        var temporaryPath = Path.Combine(scanDirectory, $"latest-{scan.ScanId}.tmp");

        await File.WriteAllTextAsync(versionPath, json, cancellationToken);
        await File.WriteAllTextAsync(temporaryPath, json, cancellationToken);
        File.Move(temporaryPath, latestPath, overwrite: true);
    }

    public async Task<RoomScanRecord?> GetLatestAsync(string roomId, CancellationToken cancellationToken)
    {
        EnsureSafeId(roomId);
        var latestPath = Path.Combine(_rootDirectory, roomId, "scans", "latest.json");
        if (!File.Exists(latestPath))
        {
            return null;
        }

        await using var stream = File.OpenRead(latestPath);
        return await JsonSerializer.DeserializeAsync<RoomScanRecord>(stream, JsonOptions, cancellationToken);
    }

    private static void EnsureSafeId(string value)
    {
        if (!Regex.IsMatch(value, "^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$", RegexOptions.CultureInvariant))
        {
            throw new ArgumentException("Room id contains invalid characters.", nameof(value));
        }
    }
}
