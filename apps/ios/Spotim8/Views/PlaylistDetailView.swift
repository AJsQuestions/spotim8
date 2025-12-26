//
//  PlaylistDetailView.swift
//  Spotim8
//
//  Detail view showing tracks in a playlist
//

import SwiftUI

struct PlaylistDetailView: View {
    let playlist: Playlist
    @StateObject private var viewModel = PlaylistDetailViewModel()
    
    var body: some View {
        List {
            if viewModel.isLoading {
                ProgressView()
                    .frame(maxWidth: .infinity, alignment: .center)
                    .padding()
            } else {
                ForEach(viewModel.tracks) { track in
                    TrackRow(track: track)
                }
            }
        }
        .navigationTitle(playlist.name)
        .navigationBarTitleDisplayMode(.large)
        .onAppear {
            viewModel.load(playlistId: playlist.id)
        }
    }
}

struct TrackRow: View {
    let track: Track
    
    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                Text(track.name)
                    .font(.headline)
                Text(track.artist)
                    .font(.subheadline)
                    .foregroundColor(.secondary)
            }
            
            Spacer()
            
            VStack(alignment: .trailing, spacing: 4) {
                Text(track.durationString)
                    .font(.caption)
                    .foregroundColor(.secondary)
                Text("\(track.popularity)")
                    .font(.caption2)
                    .foregroundColor(.secondary)
            }
        }
        .padding(.vertical, 4)
    }
}

class PlaylistDetailViewModel: ObservableObject {
    @Published var tracks: [Track] = []
    @Published var isLoading = false
    
    private let baseURL: String
    private let libraryService: LibraryService
    
    init() {
        let urlKey = "spotim8_server_url"
        self.baseURL = UserDefaults.standard.string(forKey: urlKey) ?? "http://192.168.1.252:5001"
        self.libraryService = LibraryService(baseURL: baseURL)
    }
    
    func load(playlistId: String) {
        isLoading = true
        
        libraryService.getPlaylistTracks(playlistId: playlistId) { [weak self] result in
            DispatchQueue.main.async {
                self?.isLoading = false
                if case .success(let tracks) = result {
                    self?.tracks = tracks
                }
            }
        }
    }
}

