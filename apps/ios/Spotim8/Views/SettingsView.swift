//
//  SettingsView.swift
//  Spotim8
//
//  Settings view for configuring server URL
//

import SwiftUI

struct SettingsView: View {
    @ObservedObject var viewModel: Spotim8ViewModel
    @Environment(\.dismiss) var dismiss
    @State private var serverURL: String = ""
    
    var body: some View {
        NavigationView {
            Form {
                Section(header: Text("Server Configuration")) {
                    TextField("Server URL", text: $serverURL)
                        .keyboardType(.URL)
                        .autocapitalization(.none)
                        .disableAutocorrection(true)
                        .placeholder(when: serverURL.isEmpty) {
                            Text("http://192.168.1.252:5001")
                                .foregroundColor(.secondary)
                        }
                    
                    Text("Enter your Mac's local IP address and port (e.g., http://192.168.1.100:5000)")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                
                Section(header: Text("Connection")) {
                    HStack {
                        Text("Status")
                        Spacer()
                        Circle()
                            .fill(viewModel.isConnected ? Color.green : Color.red)
                            .frame(width: 12, height: 12)
                        Text(viewModel.isConnected ? "Connected" : "Not Connected")
                            .foregroundColor(.secondary)
                    }
                    
                    Button("Test Connection") {
                        viewModel.checkConnection()
                    }
                }
            }
            .navigationTitle("Settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Cancel") {
                        dismiss()
                    }
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Save") {
                        viewModel.baseURL = serverURL
                        dismiss()
                    }
                }
            }
            .onAppear {
                serverURL = viewModel.baseURL
            }
        }
    }
}

extension View {
    func placeholder<Content: View>(
        when shouldShow: Bool,
        alignment: Alignment = .leading,
        @ViewBuilder placeholder: () -> Content) -> some View {
        
        ZStack(alignment: alignment) {
            placeholder().opacity(shouldShow ? 1 : 0)
            self
        }
    }
}

