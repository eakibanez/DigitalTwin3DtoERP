import ARKit
import RoomPlan
import SwiftUI
import UIKit

@main
struct RoomPlanScannerApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
        }
    }
}

struct RoomSurfacePayload: Codable {
    let id: String
    let kind: String
    let transform: [Float]
    let dimensions: [Float]
}

struct RoomScanPayload: Encodable {
    let buildingId: String
    let floorId: String
    let coordinateSystem: String
    let surfaces: [RoomSurfacePayload]
}

struct RoomScanResponse: Decodable {
    let scanId: String
    let roomName: String
    let surfaces: [RoomSurfacePayload]
}

@MainActor
final class RoomCaptureModel: ObservableObject {
    @Published var isScanning = false
    @Published var capturedRoom: CapturedRoom?
    @Published var status = "Choose a room, then start scanning."
    var session: RoomCaptureSession?

    func start() {
        capturedRoom = nil
        status = "Move slowly and scan each wall, door, and window."
        isScanning = true
    }

    func stop() {
        isScanning = false
        session?.stop(pauseARSession: true)
    }

    func finish(room: CapturedRoom?, error: Error?) {
        if let error {
            status = "Scan failed: \(error.localizedDescription)"
            capturedRoom = nil
        } else if let room {
            capturedRoom = room
            status = "Scan ready. Review the surface count, then upload."
        }
        isScanning = false
    }
}

struct RoomCaptureRepresentable: UIViewRepresentable {
    @ObservedObject var model: RoomCaptureModel

    func makeCoordinator() -> Coordinator {
        Coordinator(model: model)
    }

    func makeUIView(context: Context) -> RoomCaptureView {
        let view = RoomCaptureView(frame: .zero)
        view.delegate = context.coordinator
        view.captureSession.delegate = context.coordinator
        model.session = view.captureSession
        view.captureSession.run(configuration: RoomCaptureSession.Configuration())
        return view
    }

    func updateUIView(_ uiView: RoomCaptureView, context: Context) {
        if !model.isScanning {
            uiView.captureSession.stop(pauseARSession: true)
        }
    }

    final class Coordinator: NSObject, RoomCaptureViewDelegate, RoomCaptureSessionDelegate {
        private let model: RoomCaptureModel

        init(model: RoomCaptureModel) {
            self.model = model
        }

        func captureView(shouldPresent roomDataForProcessing: CapturedRoomData, error: Error?) -> Bool {
            true
        }

        func captureView(didPresent processedResult: CapturedRoom, error: Error?) {
            Task { @MainActor in
                model.finish(room: processedResult, error: error)
            }
        }

        func captureSession(_ session: RoomCaptureSession, didEndWith data: CapturedRoomData, error: Error?) {
            if let error {
                Task { @MainActor in model.finish(room: nil, error: error) }
            }
        }
    }
}

struct ContentView: View {
    @StateObject private var captureModel = RoomCaptureModel()
    @State private var apiBaseURL = "https://YOUR-TUNNEL.trycloudflare.com/api/v1"
    @State private var accessToken = ""
    @State private var buildingId = "BLDG-A"
    @State private var floorId = "FLOOR-1"
    @State private var roomId = "ROOM-A101"
    @State private var isUploading = false

    private let roomsByFloor: [String: [(id: String, name: String)]] = [
        "FLOOR-1": [("ROOM-A101", "Room A101"), ("ROOM-A102", "Room A102")],
        "FLOOR-2": [("ROOM-A201", "Room A201")]
    ]

    var body: some View {
        NavigationStack {
            Form {
                Section("Location") {
                    TextField("Building ID", text: $buildingId)
                        .textInputAutocapitalization(.characters)
                    Picker("Floor", selection: $floorId) {
                        Text("Floor 1").tag("FLOOR-1")
                        Text("Floor 2").tag("FLOOR-2")
                    }
                    .onChange(of: floorId) { _, newFloor in
                        roomId = roomsByFloor[newFloor]?.first?.id ?? ""
                    }
                    Picker("Room", selection: $roomId) {
                        ForEach(roomsByFloor[floorId] ?? [], id: \.id) { room in
                            Text(room.name).tag(room.id)
                        }
                    }
                    TextField("API base URL", text: $apiBaseURL)
                        .keyboardType(.URL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    SecureField("Room scan access token", text: $accessToken)
                }

                Section("Room scan") {
                    if captureModel.isScanning {
                        RoomCaptureRepresentable(model: captureModel)
                            .frame(height: 360)
                            .clipShape(RoundedRectangle(cornerRadius: 12))
                        Button("Finish scan") {
                            captureModel.stop()
                        }
                        .tint(.orange)
                    } else {
                        Button("Start LiDAR room scan") {
                            captureModel.start()
                        }
                        .disabled(!RoomCaptureSession.isSupported)
                    }

                    Text(captureModel.status)
                        .font(.footnote)
                        .foregroundStyle(.secondary)

                    if let room = captureModel.capturedRoom {
                        let surfaces = surfacePayloads(for: room)
                        Text("\(surfaces.count) surfaces captured")
                        Button {
                            Task { await upload(room: room) }
                        } label: {
                            if isUploading {
                                ProgressView()
                            } else {
                                Text("Upload scan to Digital Twin")
                            }
                        }
                        .disabled(isUploading || surfaces.isEmpty)
                    }
                }
            }
            .navigationTitle("RoomPlan Scanner")
        }
    }

    private func surfacePayloads(for room: CapturedRoom) -> [RoomSurfacePayload] {
        room.walls.map { payload($0, kind: "wall") }
            + room.doors.map { payload($0, kind: "door") }
            + room.windows.map { payload($0, kind: "window") }
            + room.openings.map { payload($0, kind: "opening") }
    }

    private func payload(_ surface: CapturedRoom.Surface, kind: String) -> RoomSurfacePayload {
        let columns = surface.transform.columns
        let transform: [Float] = [
            columns.0.x, columns.0.y, columns.0.z, columns.0.w,
            columns.1.x, columns.1.y, columns.1.z, columns.1.w,
            columns.2.x, columns.2.y, columns.2.z, columns.2.w,
            columns.3.x, columns.3.y, columns.3.z, columns.3.w
        ]
        return RoomSurfacePayload(
            id: surface.identifier.uuidString,
            kind: kind,
            transform: transform,
            dimensions: [surface.dimensions.x, surface.dimensions.y, surface.dimensions.z]
        )
    }

    @MainActor
    private func upload(room: CapturedRoom) async {
        guard let base = URL(string: apiBaseURL.trimmingCharacters(in: .whitespacesAndNewlines)),
              let scheme = base.scheme, scheme == "https" || scheme == "http" else {
            captureModel.status = "Enter a valid HTTPS tunnel URL or local API URL."
            return
        }

        isUploading = true
        defer { isUploading = false }
        do {
            var endpoint = base
            endpoint.append(path: "rooms/\(roomId)/scans")
            var request = URLRequest(url: endpoint)
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.setValue(accessToken, forHTTPHeaderField: "X-Room-Scan-Token")
            request.httpBody = try JSONEncoder().encode(
                RoomScanPayload(
                    buildingId: buildingId,
                    floorId: floorId,
                    coordinateSystem: "roomplan-local-y-up-meters",
                    surfaces: surfacePayloads(for: room)
                )
            )
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse else {
                throw UploadError.invalidResponse
            }
            guard (200..<300).contains(httpResponse.statusCode) else {
                let detail = String(data: data, encoding: .utf8) ?? "No response details"
                throw UploadError.server(httpResponse.statusCode, detail)
            }
            let result = try JSONDecoder().decode(RoomScanResponse.self, from: data)
            captureModel.status = "Uploaded \(result.surfaces.count) surfaces for \(result.roomName) (scan \(result.scanId))."
        } catch {
            captureModel.status = "Upload failed: \(error.localizedDescription)"
        }
    }
}

enum UploadError: LocalizedError {
    case invalidResponse
    case server(Int, String)

    var errorDescription: String? {
        switch self {
        case .invalidResponse:
            return "The API returned an invalid response."
        case let .server(status, detail):
            return "API returned \(status): \(detail)"
        }
    }
}
