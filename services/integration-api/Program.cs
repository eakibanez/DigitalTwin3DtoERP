using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;

var builder = WebApplication.CreateBuilder(args);
builder.WebHost.ConfigureKestrel(options => options.Limits.MaxRequestBodySize = 1_000_000);
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();
builder.Services.AddCors(options => options.AddDefaultPolicy(policy =>
    policy.AllowAnyOrigin().AllowAnyHeader().AllowAnyMethod()));
builder.Services.AddSingleton<RoomScanStore>();

var app = builder.Build();
app.UseCors();
app.UseSwagger();
app.UseSwaggerUI();

var buildings = new[]
{
    new Building("BLDG-A", "Demo Building A")
};
var floors = new[]
{
    new Floor("FLOOR-1", "BLDG-A", "Floor 1"),
    new Floor("FLOOR-2", "BLDG-A", "Floor 2")
};
var rooms = new[]
{
    new Room("ROOM-A101", "FLOOR-1", "Room A101"),
    new Room("ROOM-A102", "FLOOR-1", "Room A102"),
    new Room("ROOM-A201", "FLOOR-2", "Room A201")
};

app.MapGet("/health/live", () => Results.Ok(new { status = "live" }));
app.MapGet("/health/ready", () => Results.Ok(new { status = "ready" }));
app.MapGet("/api/v1/warehouses", () => Results.Ok(new[] { new { id = "WH-BKK-01", name = "Bangkok Distribution" } }));
app.MapGet("/api/v1/items", (string? warehouseId) => Results.Ok(new[] { new { id = "ITEM-204", name = "Pallet scanner", warehouseId = warehouseId ?? "WH-BKK-01" } }));
app.MapGet("/api/v1/inventory", () => Results.Ok(new[] { new { itemId = "ITEM-204", quantity = 18, status = "available" } }));
app.MapGet("/api/v1/receiving", () => Results.Ok(Array.Empty<object>()));
app.MapGet("/api/v1/picking", () => Results.Ok(Array.Empty<object>()));
app.MapGet("/api/v1/work-orders", () => Results.Ok(new[] { new { id = "WO-4821", status = "open" } }));
app.MapGet("/api/v1/twin/scenes/{warehouseId}", (string warehouseId) => Results.Ok(new
{
    warehouseId,
    coordinateSystem = "warehouse-floor",
    revision = "demo-1",
    entities = new[] { new { id = "F-204", type = "forklift", x = 1, y = .4, z = .5, confidence = .94 } }
}));

app.MapGet("/api/v1/buildings", () => Results.Ok(buildings));
app.MapGet("/api/v1/buildings/{buildingId}/floors", (string buildingId) =>
    buildings.Any(building => building.Id == buildingId)
        ? Results.Ok(floors.Where(floor => floor.BuildingId == buildingId))
        : Results.NotFound());
app.MapGet("/api/v1/floors/{floorId}/rooms", (string floorId) =>
    floors.Any(floor => floor.Id == floorId)
        ? Results.Ok(rooms.Where(room => room.FloorId == floorId))
        : Results.NotFound());

app.MapPost("/api/v1/rooms/{roomId}/scans", async (string roomId, CreateRoomScanRequest request, HttpRequest httpRequest, IConfiguration configuration, RoomScanStore store, CancellationToken cancellationToken) =>
{
    var accessError = ValidateScanAccess(httpRequest, configuration);
    if (accessError is not null)
    {
        return accessError;
    }

    var room = rooms.SingleOrDefault(candidate => candidate.Id == roomId);
    if (room is null || room.FloorId != request.FloorId ||
        floors.SingleOrDefault(candidate => candidate.Id == request.FloorId)?.BuildingId != request.BuildingId)
    {
        return Results.NotFound();
    }

    if (!IsSafeId(request.BuildingId) || !IsSafeId(request.FloorId) || !IsSafeId(roomId))
    {
        return Results.ValidationProblem(new Dictionary<string, string[]>
        {
            ["ids"] = ["Building, floor, and room IDs contain invalid characters."]
        });
    }

    var validationErrors = ValidateScan(request);
    if (validationErrors.Count > 0)
    {
        return Results.ValidationProblem(validationErrors);
    }

    var scan = new RoomScanRecord(
        Guid.NewGuid().ToString("N"),
        request.BuildingId,
        request.FloorId,
        roomId,
        room.Name,
        DateTimeOffset.UtcNow,
        request.CoordinateSystem,
        "meters",
        request.Surfaces);

    await store.SaveAsync(scan, cancellationToken);
    return Results.Created($"/api/v1/rooms/{roomId}/scans/{scan.ScanId}", scan);
});

app.MapGet("/api/v1/rooms/{roomId}/scans/latest", async (string roomId, HttpRequest httpRequest, IConfiguration configuration, RoomScanStore store, CancellationToken cancellationToken) =>
{
    var accessError = ValidateScanAccess(httpRequest, configuration);
    if (accessError is not null)
    {
        return accessError;
    }

    if (!rooms.Any(room => room.Id == roomId))
    {
        return Results.NotFound();
    }

    var scan = await store.GetLatestAsync(roomId, cancellationToken);
    return scan is null ? Results.NotFound() : Results.Ok(scan);
});

app.Run();

static bool IsSafeId(string value) =>
    Regex.IsMatch(value, "^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$", RegexOptions.CultureInvariant);

static IResult? ValidateScanAccess(HttpRequest request, IConfiguration configuration)
{
    var configuredToken = configuration["ROOM_SCAN_ACCESS_TOKEN"];
    if (string.IsNullOrWhiteSpace(configuredToken))
    {
        return Results.Problem("Room scan access is not configured.", statusCode: StatusCodes.Status503ServiceUnavailable);
    }

    var suppliedToken = request.Headers["X-Room-Scan-Token"].ToString();
    var expectedBytes = Encoding.UTF8.GetBytes(configuredToken);
    var suppliedBytes = Encoding.UTF8.GetBytes(suppliedToken);
    return CryptographicOperations.FixedTimeEquals(expectedBytes, suppliedBytes)
        ? null
        : Results.Unauthorized();
}

static Dictionary<string, string[]> ValidateScan(CreateRoomScanRequest request)
{
    var errors = new Dictionary<string, string[]>();
    if (request.CoordinateSystem != "roomplan-local-y-up-meters")
    {
        errors["coordinateSystem"] = ["Expected roomplan-local-y-up-meters."];
    }

    if (request.Surfaces is null || request.Surfaces.Count is < 1 or > 500)
    {
        errors["surfaces"] = ["A scan must contain between 1 and 500 surfaces."];
        return errors;
    }

    for (var index = 0; index < request.Surfaces.Count; index++)
    {
        var surface = request.Surfaces[index];
        if (string.IsNullOrWhiteSpace(surface.Id) || surface.Id.Length > 64 ||
            surface.Kind is not ("wall" or "door" or "window" or "opening") ||
            surface.Transform is null || surface.Transform.Length != 16 ||
            surface.Dimensions is null || surface.Dimensions.Length != 3 ||
            surface.Transform.Any(value => !float.IsFinite(value)) ||
            surface.Dimensions.Any(value => !float.IsFinite(value) || value <= 0 || value > 50))
        {
            errors[$"surfaces[{index}]"] = ["Surface id, kind, 16 finite transform values, and 3 positive dimensions (up to 50m) are required."];
        }
    }

    return errors;
}

public sealed record Building(string Id, string Name);
public sealed record Floor(string Id, string BuildingId, string Name);
public sealed record Room(string Id, string FloorId, string Name);
public sealed record RoomSurface(string Id, string Kind, float[] Transform, float[] Dimensions);
public sealed record CreateRoomScanRequest(string BuildingId, string FloorId, string CoordinateSystem, List<RoomSurface> Surfaces);
public sealed record RoomScanRecord(
    string ScanId,
    string BuildingId,
    string FloorId,
    string RoomId,
    string RoomName,
    DateTimeOffset CapturedAt,
    string CoordinateSystem,
    string Units,
    IReadOnlyList<RoomSurface> Surfaces);
