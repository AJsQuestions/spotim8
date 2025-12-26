//
//  AutomationView.swift
//  Spotim8
//
//  Playlist automation controls
//

import SwiftUI

struct AutomationView: View {
    @StateObject private var viewModel = Spotim8ViewModel()
    @State private var showSettings = false
    
    var body: some View {
        NavigationView {
            VStack(spacing: 24) {
                // Header
                VStack(spacing: 8) {
                    Image(systemName: "gearshape.2")
                        .font(.system(size: 60))
                        .foregroundColor(.green)
                    
                    Text("Playlist Automation")
                        .font(.largeTitle)
                        .fontWeight(.bold)
                    
                    Text("Sync & Manage Playlists")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                }
                .padding(.top, 40)
                
                Spacer()
                
                // Connection Status
                HStack {
                    Circle()
                        .fill(viewModel.isConnected ? Color.green : Color.red)
                        .frame(width: 12, height: 12)
                    Text(viewModel.isConnected ? "Connected" : "Not Connected")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                }
                .padding(.bottom, 8)
                
                // Action Buttons
                VStack(spacing: 16) {
                    // Sync Button
                    Button(action: {
                        viewModel.triggerSync()
                    }) {
                        HStack {
                            Image(systemName: "arrow.clockwise")
                            Text("Run Sync Automation")
                                .fontWeight(.semibold)
                        }
                        .frame(maxWidth: .infinity)
                        .padding()
                        .background(Color.green)
                        .foregroundColor(.white)
                        .cornerRadius(12)
                    }
                    .disabled(viewModel.isLoading || !viewModel.isConnected)
                    
                    // Analysis Button
                    Button(action: {
                        viewModel.triggerAnalysis()
                    }) {
                        HStack {
                            Image(systemName: "chart.bar")
                            Text("Run Static Analysis")
                                .fontWeight(.semibold)
                        }
                        .frame(maxWidth: .infinity)
                        .padding()
                        .background(Color.blue)
                        .foregroundColor(.white)
                        .cornerRadius(12)
                    }
                    .disabled(viewModel.isLoading || !viewModel.isConnected)
                }
                .padding(.horizontal, 24)
                
                // Loading Indicator
                if viewModel.isLoading {
                    ProgressView()
                        .padding()
                }
                
                // Status/Results
                if let currentTask = viewModel.currentTask {
                    ScrollView {
                        VStack(alignment: .leading, spacing: 12) {
                            HStack {
                                Text("Status")
                                    .font(.headline)
                                Spacer()
                                Text(currentTask.status.capitalized)
                                    .font(.subheadline)
                                    .padding(.horizontal, 12)
                                    .padding(.vertical, 4)
                                    .background(statusColor(for: currentTask.status))
                                    .foregroundColor(.white)
                                    .cornerRadius(8)
                            }
                            
                            if let startedAt = currentTask.startedAt {
                                Text("Started: \(formatDate(startedAt))")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            }
                            
                            if let completedAt = currentTask.completedAt {
                                Text("Completed: \(formatDate(completedAt))")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            }
                            
                            // Stats (for analysis)
                            if let stats = currentTask.stats {
                                Divider()
                                Text("Statistics")
                                    .font(.headline)
                                    .padding(.top, 8)
                                
                                StatRow(label: "Playlists", value: "\(stats.totalPlaylists)")
                                StatRow(label: "Tracks", value: "\(stats.totalTracks)")
                                StatRow(label: "Artists", value: "\(stats.totalArtists)")
                                StatRow(label: "Total Hours", value: String(format: "%.1f", stats.totalHours))
                            }
                            
                            // Output Log
                            if !currentTask.output.isEmpty {
                                Divider()
                                Text("Output")
                                    .font(.headline)
                                    .padding(.top, 8)
                                
                                ForEach(currentTask.output, id: \.self) { line in
                                    Text(line)
                                        .font(.system(.caption, design: .monospaced))
                                        .foregroundColor(.secondary)
                                        .padding(.vertical, 2)
                                }
                            }
                        }
                        .padding()
                        .background(Color(.systemGray6))
                        .cornerRadius(12)
                    }
                    .frame(maxHeight: 300)
                    .padding(.horizontal, 24)
                }
                
                Spacer()
            }
            .navigationTitle("")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button(action: {
                        showSettings = true
                    }) {
                        Image(systemName: "gearshape")
                    }
                }
            }
            .sheet(isPresented: $showSettings) {
                SettingsView(viewModel: viewModel)
            }
            .onAppear {
                viewModel.checkConnection()
            }
        }
    }
    
    private func statusColor(for status: String) -> Color {
        switch status.lowercased() {
        case "completed":
            return .green
        case "running":
            return .blue
        case "failed", "error":
            return .red
        default:
            return .gray
        }
    }
    
    private func formatDate(_ dateString: String) -> String {
        let formatter = ISO8601DateFormatter()
        if let date = formatter.date(from: dateString) {
            let displayFormatter = DateFormatter()
            displayFormatter.dateStyle = .none
            displayFormatter.timeStyle = .medium
            return displayFormatter.string(from: date)
        }
        return dateString
    }
}

struct StatRow: View {
    let label: String
    let value: String
    
    var body: some View {
        HStack {
            Text(label)
                .foregroundColor(.secondary)
            Spacer()
            Text(value)
                .fontWeight(.semibold)
        }
    }
}

