import SwiftUI
import UIKit

private enum AppScreen {
    case key
    case dashboard
}

private struct KeyValidationResponse: Decodable {
    let valid: Bool
    let durationDays: Int
    let durationLabel: String
    let remainingSeconds: Int
}

struct ContentView: View {
    @State private var screen: AppScreen = .key
    @State private var key = ""
    @State private var keyValidation: KeyValidationResponse?
    @State private var validationStartedAt: TimeInterval = 0
    @State private var isValidating = false
    @State private var validationError: String?
    @State private var dashboardTab = "PANEL"
    @State private var enabledOptions: Set<String> = ["Estado del panel"]
    @FocusState private var keyFieldFocused: Bool
    private let validationAPIURL = "https://YOUR_DOMAIN/api/validate"

    private let panelSettings = [
        ("Estado del panel", "circle.inset.filled"),
        ("Indicador de estado", "waveform.path"),
        ("Modo compacto", "rectangle.compress.vertical")
    ]
    private let visualSettings = [
        ("Resaltar selección", "sparkle"),
        ("Animaciones suaves", "circle.dotted"),
        ("Contraste alto", "circle.lefthalf.filled")
    ]

    var body: some View {
        ZStack {
            GeometryReader { geometry in
                LinearGradient(
                    colors: [Color(red: 0.075, green: 0.055, blue: 0.045), .black],
                    startPoint: .top,
                    endPoint: .bottom
                )
                .overlay(alignment: .top) {
                    RadialGradient(
                        colors: [Color.orange.opacity(0.16), .clear],
                        center: .top,
                        startRadius: 5,
                        endRadius: geometry.size.height * 0.55
                    )
                }
            }
            .ignoresSafeArea()

            VStack(spacing: 0) {
                header

                if screen == .key {
                    Image("DRTBackground")
                        .resizable()
                        .scaledToFit()
                        .frame(height: 192)
                        .frame(maxWidth: .infinity)
                        .shadow(color: .orange.opacity(0.2), radius: 18, y: 5)
                        .accessibilityHidden(true)
                }

                if screen == .key {
                    Spacer(minLength: 10)
                }

                switch screen {
                case .key:
                    keyView
                case .dashboard:
                    dashboardView
                }

                if screen == .key {
                    Spacer(minLength: 10)

                    Text("PANEL DE ACCESO · SIN CONEXIÓN A JUEGOS")
                        .font(.system(size: 9, weight: .medium, design: .monospaced))
                        .tracking(1.2)
                        .foregroundStyle(.white.opacity(0.34))
                        .multilineTextAlignment(.center)
                        .padding(.bottom, 18)
                }
            }
            .padding(.horizontal, 24)
        }
        .preferredColorScheme(.dark)
    }

    private var header: some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 3) {
                Text("DRT PANEL")
                    .font(.system(size: 16, weight: .black, design: .rounded))
                    .tracking(2)
                    .foregroundStyle(.white)
            }

            Spacer()

            Text("DRT IO")
                .font(.system(size: 9, weight: .bold, design: .monospaced))
                .tracking(1)
                .foregroundStyle(.white.opacity(0.55))
        }
        .padding(.top, 14)
    }

    private var keyView: some View {
        VStack(alignment: .leading, spacing: 22) {
            title(eyebrow: "EL MEJOR ACCESO DRT IOS", heading: "Bienvenido a DRT")

            Text("Introduce la key que te dio el vendedor de DRT IO.")
                .font(.system(size: 14))
                .foregroundStyle(.white.opacity(0.55))
                .fixedSize(horizontal: false, vertical: true)

            VStack(alignment: .leading, spacing: 9) {
                HStack {
                    Text("KEY DE ACCESO")
                        .font(.system(size: 10, weight: .bold, design: .monospaced))
                        .tracking(1.2)
                        .foregroundStyle(.white.opacity(0.88))
                    Spacer()
                    Label("KEY PERSONAL", systemImage: "key.fill")
                        .font(.system(size: 9, weight: .medium, design: .monospaced))
                        .foregroundStyle(Color(red: 0.78, green: 0.65, blue: 0.47))
                }

                HStack(spacing: 12) {
                    Image(systemName: "key.horizontal.fill")
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundStyle(.orange)
                        .frame(width: 32, height: 32)
                        .background(Color.orange.opacity(0.08))
                        .clipShape(RoundedRectangle(cornerRadius: 10))

                    SecureField("DRT-WEEK 0000", text: $key)
                        .textInputAutocapitalization(.characters)
                        .autocorrectionDisabled()
                        .font(.system(size: 14, weight: .medium, design: .monospaced))
                        .focused($keyFieldFocused)
                }
                .padding(.horizontal, 14)
                .frame(height: 60)
                .background(
                    LinearGradient(
                        colors: [Color(red: 0.11, green: 0.11, blue: 0.13), panelColor],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 14)
                        .stroke(keyFieldFocused ? Color.orange.opacity(0.72) : borderColor, lineWidth: 1)
                )
                .clipShape(RoundedRectangle(cornerRadius: 14))

                Text("Tu key es personal. Si no la tienes, solicítala a tu vendedor.")
                    .font(.system(size: 11))
                    .foregroundStyle(.white.opacity(0.43))
                    .fixedSize(horizontal: false, vertical: true)

                if let validationError {
                    Text(validationError)
                        .font(.system(size: 11, weight: .medium))
                        .foregroundStyle(.orange)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }

            Button {
                Task {
                    await validateKeyAndContinue()
                }
            } label: {
                primaryButtonLabel(isValidating ? "VERIFYING..." : "CONTINUAR", icon: "arrow.right")
            }
            .buttonStyle(.plain)
            .disabled(isValidating)
            .accessibilityHint("Abre el panel de configuración")
        }
        .padding(22)
        .background(panelColor.opacity(0.72))
        .overlay(RoundedRectangle(cornerRadius: 22).stroke(borderColor, lineWidth: 1))
        .clipShape(RoundedRectangle(cornerRadius: 22))
    }

    private var dashboardView: some View {
        ScrollView(showsIndicators: false) {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("DRT IOS / PANEL DE AIMBOTS")
                            .font(.system(size: 9, weight: .bold, design: .monospaced))
                            .tracking(1.2)
                            .foregroundStyle(Color(red: 1, green: 0.79, blue: 0.55))
                        Text("PANEL PERSONAL")
                            .font(.system(size: 8, weight: .medium, design: .monospaced))
                            .tracking(1)
                            .foregroundStyle(.white.opacity(0.42))
                    }
                    Spacer()
                    Label("LISTO", systemImage: "circle.fill")
                        .font(.system(size: 8, weight: .bold, design: .monospaced))
                        .foregroundStyle(Color(red: 1, green: 0.62, blue: 0.24))
                }

                gameCard

                statusCard(
                    label: "VERSIÓN DE iOS",
                    value: "iOS \(UIDevice.current.systemVersion)",
                    icon: "iphone"
                )

                VStack(alignment: .leading, spacing: 11) {
                    HStack {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("DRT PANEL")
                                .font(.system(size: 10, weight: .heavy, design: .monospaced))
                                .tracking(1)
                            Text("PREFERENCIAS DE INTERFAZ")
                                .font(.system(size: 8, weight: .medium, design: .monospaced))
                                .tracking(0.8)
                                .foregroundStyle(.white.opacity(0.45))
                        }
                        Spacer()
                        Text("3 AJUSTES")
                            .font(.system(size: 8, weight: .bold, design: .monospaced))
                            .foregroundStyle(.white.opacity(0.68))
                            .padding(.horizontal, 9)
                            .padding(.vertical, 7)
                            .background(Color.orange.opacity(0.16))
                            .clipShape(Capsule())
                    }

                    keyTimeRemainingCard
                    .padding(10)
                    .background(
                        LinearGradient(
                            colors: [Color(red: 0.20, green: 0.12, blue: 0.07), Color(red: 0.07, green: 0.055, blue: 0.045)],
                            startPoint: .leading,
                            endPoint: .trailing
                        )
                    )
                    .clipShape(RoundedRectangle(cornerRadius: 14))

                    HStack(spacing: 7) {
                        tabButton("PANEL", icon: "square.grid.2x2")
                        tabButton("VISUAL", icon: "sparkles")
                    }

                    ForEach(currentSettings, id: \.0) { setting in
                        settingRow(setting.0, icon: setting.1)
                    }

                    Text("Ajustes únicamente visuales. No controlan ni modifican el juego.")
                        .font(.system(size: 9, weight: .medium, design: .monospaced))
                        .foregroundStyle(.white.opacity(0.58))
                        .multilineTextAlignment(.center)
                        .frame(maxWidth: .infinity)

                    Button {
                        key = ""
                        keyValidation = nil
                        validationError = nil
                        enabledOptions = ["Estado del panel"]
                        dashboardTab = "PANEL"
                        screen = .key
                    } label: {
                        Label("VOLVER AL ACCESO", systemImage: "arrow.left")
                            .font(.system(size: 9, weight: .bold, design: .monospaced))
                            .tracking(0.7)
                            .foregroundStyle(.white.opacity(0.58))
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 7)
                    }
                    .buttonStyle(.plain)
                }
                .padding(13)
                .background(
                    LinearGradient(
                        colors: [Color(red: 0.14, green: 0.09, blue: 0.055), Color(red: 0.065, green: 0.052, blue: 0.043)],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
                .overlay(RoundedRectangle(cornerRadius: 18).stroke(Color.orange.opacity(0.27), lineWidth: 1))
                .clipShape(RoundedRectangle(cornerRadius: 18))

                Text("DRT IOS · PANEL DE CONFIGURACIÓN LOCAL")
                    .font(.system(size: 8, weight: .medium, design: .monospaced))
                    .tracking(0.7)
                    .foregroundStyle(.white.opacity(0.34))
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 7)
            }
            .padding(.vertical, 12)
        }
    }

    private var gameCard: some View {
        Image("DRTBackground")
            .resizable()
            .scaledToFit()
            .frame(maxWidth: .infinity)
            .frame(height: 150)
            .blendMode(.screen)
            .shadow(color: .orange.opacity(0.3), radius: 16)
            .accessibilityHidden(true)
    }

    private var keyTimeRemainingCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 10) {
                Image(systemName: "clock")
                    .font(.system(size: 17, weight: .medium))
                    .foregroundStyle(Color(red: 1, green: 0.82, blue: 0.62))
                    .frame(width: 38, height: 38)
                    .background(Color.orange.opacity(0.12))
                    .clipShape(Circle())
                    .overlay(Circle().stroke(Color.orange.opacity(0.65), lineWidth: 1))
                VStack(alignment: .leading, spacing: 4) {
                    Text("DRT IOS KEY TIME LEFT")
                        .font(.system(size: 8, weight: .bold, design: .monospaced))
                        .tracking(0.8)
                        .foregroundStyle(Color(red: 1, green: 0.76, blue: 0.49))
                    Text(keyValidation?.durationLabel ?? "")
                        .font(.system(size: 9, weight: .semibold))
                        .foregroundStyle(.white.opacity(0.9))
                }
            }

            TimelineView(.periodic(from: .now, by: 1)) { _ in
                let remaining = secondsRemaining
                if remaining == 0 {
                    Text("KEY EXPIRED")
                        .font(.system(size: 11, weight: .bold, design: .monospaced))
                        .foregroundStyle(.orange)
                } else {
                    HStack(spacing: 5) {
                        countdownUnit(remaining / 86_400, label: "DAYS")
                        countdownUnit((remaining % 86_400) / 3_600, label: "HRS")
                        countdownUnit((remaining % 3_600) / 60, label: "MINS")
                        countdownUnit(remaining % 60, label: "SECS")
                    }
                }
            }
        }
    }

    private var secondsRemaining: Int {
        guard keyValidation != nil else { return 0 }
        let elapsed = Int(ProcessInfo.processInfo.systemUptime - validationStartedAt)
        return max(0, (keyValidation?.remainingSeconds ?? 0) - elapsed)
    }

    private func countdownUnit(_ value: Int, label: String) -> some View {
        VStack(spacing: 3) {
            Text(String(format: "%02d", value))
                .font(.system(size: 15, weight: .bold, design: .monospaced))
                .foregroundStyle(.white)
                .monospacedDigit()
            Text(label)
                .font(.system(size: 7, weight: .bold, design: .monospaced))
                .foregroundStyle(.white.opacity(0.58))
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 7)
        .background(Color.black.opacity(0.22))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    @MainActor
    private func validateKeyAndContinue() async {
        let submittedKey = key.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        guard !submittedKey.isEmpty else {
            validationError = "Enter your key."
            return
        }
        guard let endpoint = URL(string: validationAPIURL),
              endpoint.scheme == "https",
              endpoint.host?.lowercased() != "your_domain" else {
            validationError = "Set the HTTPS validation API URL before using keys."
            return
        }

        isValidating = true
        validationError = nil
        defer { isValidating = false }

        do {
            var request = URLRequest(url: endpoint)
            request.httpMethod = "POST"
            request.timeoutInterval = 15
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONSerialization.data(withJSONObject: ["key": submittedKey])
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse else {
                validationError = "The validation service returned an invalid response."
                return
            }
            guard httpResponse.statusCode == 200 else {
                switch httpResponse.statusCode {
                case 401:
                    validationError = "This key is invalid, expired, or revoked."
                case 429:
                    validationError = "Too many attempts. Please try again later."
                default:
                    validationError = "The validation service is unavailable. Please try again later."
                }
                return
            }

            let result = try JSONDecoder.keyValidationDecoder.decode(
                KeyValidationResponse.self,
                from: data
            )
            let expectedLabels = [7: "WEEK", 15: "2 WEEKS", 30: "1 MONTH"]
            guard result.valid,
                  result.remainingSeconds > 0,
                  expectedLabels[result.durationDays] == result.durationLabel else {
                validationError = "This key is invalid, expired, or revoked."
                return
            }

            keyValidation = result
            validationStartedAt = ProcessInfo.processInfo.systemUptime
            keyFieldFocused = false
            screen = .dashboard
        } catch {
            validationError = "Could not reach the validation service. Check your connection."
        }
    }

    private var currentSettings: [(String, String)] {
        dashboardTab == "PANEL" ? panelSettings : visualSettings
    }

    private extension JSONDecoder {
        static var keyValidationDecoder: JSONDecoder {
            let decoder = JSONDecoder()
            decoder.keyDecodingStrategy = .convertFromSnakeCase
            return decoder
        }
    }

    private func statusCard(label: String, value: String, icon: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Image(systemName: icon)
                .font(.system(size: 9, weight: .semibold))
                .foregroundStyle(.white.opacity(0.6))
            Text(label)
                .font(.system(size: 7, weight: .bold, design: .monospaced))
                .tracking(0.7)
                .foregroundStyle(.white.opacity(0.45))
            Text(value)
                .font(.system(size: 9, weight: .bold))
                .foregroundStyle(.white.opacity(0.88))
                .lineLimit(1)
                .minimumScaleFactor(0.8)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(9)
        .background(
            LinearGradient(
                colors: [Color(red: 0.16, green: 0.10, blue: 0.06), Color(red: 0.07, green: 0.055, blue: 0.045)],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
        )
        .overlay(RoundedRectangle(cornerRadius: 13).stroke(Color.orange.opacity(0.2), lineWidth: 1))
        .clipShape(RoundedRectangle(cornerRadius: 13))
    }

    private func tabButton(_ title: String, icon: String) -> some View {
        let isSelected = dashboardTab == title
        return Button {
            dashboardTab = title
        } label: {
            Label(title, systemImage: icon)
                .font(.system(size: 8, weight: .heavy, design: .monospaced))
                .tracking(0.5)
                .foregroundStyle(isSelected ? Color(red: 0.16, green: 0.07, blue: 0.02) : .white.opacity(0.68))
                .frame(maxWidth: .infinity)
                .frame(height: 35)
                .background {
                    if isSelected {
                        LinearGradient(
                            colors: [Color(red: 1, green: 0.84, blue: 0.63), Color(red: 0.94, green: 0.49, blue: 0.2)],
                            startPoint: .leading,
                            endPoint: .trailing
                        )
                    } else {
                        panelColor
                    }
                }
                .clipShape(RoundedRectangle(cornerRadius: 11))
        }
        .buttonStyle(.plain)
    }

    private func settingRow(_ name: String, icon: String) -> some View {
        Toggle(isOn: toggleBinding(for: name)) {
            HStack(spacing: 10) {
                Image(systemName: icon)
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(Color(red: 1, green: 0.73, blue: 0.4))
                    .frame(width: 28, height: 28)
                    .background(Color(red: 0.30, green: 0.15, blue: 0.07))
                    .clipShape(RoundedRectangle(cornerRadius: 9))
                Text(name.uppercased())
                    .font(.system(size: 8, weight: .bold, design: .monospaced))
                    .tracking(0.55)
                    .foregroundStyle(.white.opacity(0.9))
            }
        }
        .tint(.orange)
        .padding(.horizontal, 9)
        .padding(.vertical, 7)
        .background(
            LinearGradient(
                colors: [Color.white.opacity(0.07), Color.white.opacity(0.025)],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
        )
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color.orange.opacity(0.16), lineWidth: 1))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private var panelColor: Color {
        Color(red: 0.075, green: 0.065, blue: 0.065)
    }

    private var borderColor: Color {
        Color.white.opacity(0.12)
    }

    private func title(eyebrow: String, heading: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(eyebrow)
                .font(.system(size: 9, weight: .bold, design: .monospaced))
                .tracking(1.5)
                .foregroundStyle(.orange)
            Text(heading)
                .font(.system(size: 25, weight: .bold, design: .rounded))
                .foregroundStyle(.white)
        }
    }

    private func primaryButtonLabel(_ label: String, icon: String) -> some View {
        HStack {
            Spacer()
            Text(label)
            Image(systemName: icon)
            Spacer()
        }
        .font(.system(size: 12, weight: .bold, design: .monospaced))
        .tracking(1.2)
        .foregroundStyle(Color(red: 0.16, green: 0.07, blue: 0.02))
        .frame(height: 52)
        .background(
            LinearGradient(
                colors: [Color(red: 1, green: 0.82, blue: 0.48), Color(red: 0.95, green: 0.48, blue: 0.18)],
                startPoint: .leading,
                endPoint: .trailing
            )
        )
        .clipShape(RoundedRectangle(cornerRadius: 14))
    }

    private func toggleBinding(for option: String) -> Binding<Bool> {
        Binding(
            get: { enabledOptions.contains(option) },
            set: { isEnabled in
                if isEnabled {
                    enabledOptions.insert(option)
                } else {
                    enabledOptions.remove(option)
                }
            }
        )
    }

}
