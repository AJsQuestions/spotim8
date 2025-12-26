//
//  LibraryModels.swift
//  Spotim8
//
//  Data models for library data
//

import Foundation

struct LibraryStats: Codable {
    let totalTracks: Int
    let totalArtists: Int
    let totalPlaylists: Int
    let totalHours: Double
    let avgPopularity: Double
    
    enum CodingKeys: String, CodingKey {
        case totalTracks = "total_tracks"
        case totalArtists = "total_artists"
        case totalPlaylists = "total_playlists"
        case totalHours = "total_hours"
        case avgPopularity = "avg_popularity"
    }
}

struct Playlist: Codable, Identifiable {
    let id: String
    let name: String
    let trackCount: Int
    let isOwned: Bool
    
    enum CodingKeys: String, CodingKey {
        case id = "playlist_id"
        case name
        case trackCount = "track_count"
        case isOwned = "is_owned"
    }
}

struct Track: Codable, Identifiable {
    let id: String
    let name: String
    let artist: String
    let durationMs: Int
    let popularity: Int
    
    enum CodingKeys: String, CodingKey {
        case id = "track_id"
        case name
        case artist
        case durationMs = "duration_ms"
        case popularity
    }
    
    var durationString: String {
        let seconds = durationMs / 1000
        let minutes = seconds / 60
        let remainingSeconds = seconds % 60
        return String(format: "%d:%02d", minutes, remainingSeconds)
    }
}

struct Artist: Codable, Identifiable {
    let id: String
    let name: String
    let popularity: Int
    let genres: [String]
    
    enum CodingKeys: String, CodingKey {
        case id = "artist_id"
        case name
        case popularity
        case genres
    }
    
    var genresString: String {
        genres.isEmpty ? "No genres" : genres.joined(separator: ", ")
    }
}

