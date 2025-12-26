//
//  LibraryService.swift
//  Spotim8
//
//  Service for fetching library data from server
//

import Foundation

class LibraryService: ObservableObject {
    private let baseURL: String
    
    init(baseURL: String) {
        self.baseURL = baseURL
    }
    
    func getStats(completion: @escaping (Result<LibraryStats, Error>) -> Void) {
        guard let url = URL(string: "\(baseURL)/library/stats") else {
            completion(.failure(NSError(domain: "Invalid URL", code: -1)))
            return
        }
        
        URLSession.shared.dataTask(with: url) { data, response, error in
            if let error = error {
                completion(.failure(error))
                return
            }
            
            guard let data = data else {
                completion(.failure(NSError(domain: "No data", code: -1)))
                return
            }
            
            do {
                let stats = try JSONDecoder().decode(LibraryStats.self, from: data)
                completion(.success(stats))
            } catch {
                completion(.failure(error))
            }
        }.resume()
    }
    
    func getPlaylists(completion: @escaping (Result<[Playlist], Error>) -> Void) {
        guard let url = URL(string: "\(baseURL)/library/playlists") else {
            completion(.failure(NSError(domain: "Invalid URL", code: -1)))
            return
        }
        
        URLSession.shared.dataTask(with: url) { data, response, error in
            if let error = error {
                completion(.failure(error))
                return
            }
            
            guard let data = data,
                  let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let playlistsArray = json["playlists"] as? [[String: Any]] else {
                completion(.failure(NSError(domain: "Invalid response", code: -1)))
                return
            }
            
            do {
                let playlistsData = try JSONSerialization.data(withJSONObject: playlistsArray)
                let playlists = try JSONDecoder().decode([Playlist].self, from: playlistsData)
                completion(.success(playlists))
            } catch {
                completion(.failure(error))
            }
        }.resume()
    }
    
    func getPlaylistTracks(playlistId: String, completion: @escaping (Result<[Track], Error>) -> Void) {
        guard let url = URL(string: "\(baseURL)/library/playlist/\(playlistId)/tracks") else {
            completion(.failure(NSError(domain: "Invalid URL", code: -1)))
            return
        }
        
        URLSession.shared.dataTask(with: url) { data, response, error in
            if let error = error {
                completion(.failure(error))
                return
            }
            
            guard let data = data,
                  let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let tracksArray = json["tracks"] as? [[String: Any]] else {
                completion(.failure(NSError(domain: "Invalid response", code: -1)))
                return
            }
            
            do {
                let tracksData = try JSONSerialization.data(withJSONObject: tracksArray)
                let tracks = try JSONDecoder().decode([Track].self, from: tracksData)
                completion(.success(tracks))
            } catch {
                completion(.failure(error))
            }
        }.resume()
    }
    
    func getArtists(completion: @escaping (Result<[Artist], Error>) -> Void) {
        guard let url = URL(string: "\(baseURL)/library/artists") else {
            completion(.failure(NSError(domain: "Invalid URL", code: -1)))
            return
        }
        
        URLSession.shared.dataTask(with: url) { data, response, error in
            if let error = error {
                completion(.failure(error))
                return
            }
            
            guard let data = data,
                  let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let artistsArray = json["artists"] as? [[String: Any]] else {
                completion(.failure(NSError(domain: "Invalid response", code: -1)))
                return
            }
            
            do {
                let artistsData = try JSONSerialization.data(withJSONObject: artistsArray)
                let artists = try JSONDecoder().decode([Artist].self, from: artistsData)
                completion(.success(artists))
            } catch {
                completion(.failure(error))
            }
        }.resume()
    }
}

