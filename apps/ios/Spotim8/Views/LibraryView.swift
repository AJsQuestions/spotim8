//
//  LibraryView.swift
//  Spotim8
//
//  Main library explorer view
//

import SwiftUI

struct LibraryView: View {
    @StateObject private var viewModel = LibraryViewModel()
    @State private var selectedTab = 0
    
    var body: some View {
        NavigationView {
            VStack(spacing: 0) {
                // Stats Header
                if let stats = viewModel.stats {
                    StatsCard(stats: stats)
                        .padding()
                }
                
                // Tab Selector
                Picker("View", selection: $selectedTab) {
                    Text("Playlists").tag(0)
                    Text("Artists").tag(1)
                }
                .pickerStyle(SegmentedPickerStyle())
                .padding(.horizontal)
                
                // Content
                if viewModel.isLoading {
                    Spacer()
                    ProgressView()
                    Spacer()
                } else {
                    TabView(selection: $selectedTab) {
                        PlaylistsListView(viewModel: viewModel)
                            .tag(0)
                        
                        ArtistsListView(viewModel: viewModel)
                            .tag(1)
                    }
                    .tabViewStyle(PageTabViewStyle(indexDisplayMode: .never))
                }
            }
            .navigationTitle("Library")
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button(action: {
                        viewModel.refresh()
                    }) {
                        Image(systemName: "arrow.clockwise")
                    }
                }
            }
            .onAppear {
                viewModel.load()
            }
        }
    }
}

struct StatsCard: View {
    let stats: LibraryStats
    
    var body: some View {
        VStack(spacing: 12) {
            HStack {
                StatItem(label: "Playlists", value: "\(stats.totalPlaylists)")
                Divider()
                StatItem(label: "Tracks", value: "\(stats.totalTracks)")
                Divider()
                StatItem(label: "Artists", value: "\(stats.totalArtists)")
            }
            
            HStack {
                StatItem(label: "Total Hours", value: String(format: "%.1f", stats.totalHours))
                Divider()
                StatItem(label: "Avg Popularity", value: "\(Int(stats.avgPopularity))")
            }
        }
        .padding()
        .background(Color(.systemGray6))
        .cornerRadius(12)
    }
}

struct StatItem: View {
    let label: String
    let value: String
    
    var body: some View {
        VStack(spacing: 4) {
            Text(value)
                .font(.title2)
                .fontWeight(.bold)
            Text(label)
                .font(.caption)
                .foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity)
    }
}

struct PlaylistsListView: View {
    @ObservedObject var viewModel: LibraryViewModel
    
    var body: some View {
        List {
            ForEach(viewModel.playlists) { playlist in
                NavigationLink(destination: PlaylistDetailView(playlist: playlist)) {
                    PlaylistRow(playlist: playlist)
                }
            }
        }
        .listStyle(PlainListStyle())
    }
}

struct PlaylistRow: View {
    let playlist: Playlist
    
    var body: some View {
        HStack {
            Image(systemName: "music.note.list")
                .font(.title2)
                .foregroundColor(.green)
                .frame(width: 40)
            
            VStack(alignment: .leading, spacing: 4) {
                Text(playlist.name)
                    .font(.headline)
                Text("\(playlist.trackCount) tracks")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            
            Spacer()
        }
        .padding(.vertical, 4)
    }
}

struct ArtistsListView: View {
    @ObservedObject var viewModel: LibraryViewModel
    
    var body: some View {
        List {
            ForEach(viewModel.artists) { artist in
                ArtistRow(artist: artist)
            }
        }
        .listStyle(PlainListStyle())
    }
}

struct ArtistRow: View {
    let artist: Artist
    
    var body: some View {
        HStack {
            Image(systemName: "person.fill")
                .font(.title2)
                .foregroundColor(.blue)
                .frame(width: 40)
            
            VStack(alignment: .leading, spacing: 4) {
                Text(artist.name)
                    .font(.headline)
                if !artist.genres.isEmpty {
                    Text(artist.genres.prefix(2).joined(separator: ", "))
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .lineLimit(1)
                }
            }
            
            Spacer()
            
            Text("\(artist.popularity)")
                .font(.caption)
                .foregroundColor(.secondary)
        }
        .padding(.vertical, 4)
    }
}

class LibraryViewModel: ObservableObject {
    @Published var stats: LibraryStats?
    @Published var playlists: [Playlist] = []
    @Published var artists: [Artist] = []
    @Published var isLoading = false
    
    private let baseURL: String
    private let libraryService: LibraryService
    
    init() {
        let urlKey = "spotim8_server_url"
        self.baseURL = UserDefaults.standard.string(forKey: urlKey) ?? "http://192.168.1.252:5001"
        self.libraryService = LibraryService(baseURL: baseURL)
    }
    
    func load() {
        isLoading = true
        
        // Load stats
        libraryService.getStats { [weak self] result in
            DispatchQueue.main.async {
                if case .success(let stats) = result {
                    self?.stats = stats
                }
            }
        }
        
        // Load playlists
        libraryService.getPlaylists { [weak self] result in
            DispatchQueue.main.async {
                self?.isLoading = false
                if case .success(let playlists) = result {
                    self?.playlists = playlists
                }
            }
        }
        
        // Load artists
        libraryService.getArtists { [weak self] result in
            DispatchQueue.main.async {
                if case .success(let artists) = result {
                    self?.artists = artists
                }
            }
        }
    }
    
    func refresh() {
        load()
    }
}

