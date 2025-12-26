//
//  AutomationService.swift
//  Spotim8
//
//  Service for playlist automation (sync and analysis)
//

import Foundation
import Combine

class Spotim8ViewModel: ObservableObject {
    @Published var isConnected = false
    @Published var isLoading = false
    @Published var currentTask: TaskStatus?
    
    private let baseURLKey = "spotim8_server_url"
    private var pollingTimer: Timer?
    
    var baseURL: String {
        get {
            UserDefaults.standard.string(forKey: baseURLKey) ?? "http://192.168.1.252:5001"
        }
        set {
            UserDefaults.standard.set(newValue, forKey: baseURLKey)
            checkConnection()
        }
    }
    
    init() {
        checkConnection()
    }
    
    func checkConnection() {
        guard let url = URL(string: "\(baseURL)/health") else {
            isConnected = false
            return
        }
        
        var request = URLRequest(url: url)
        request.timeoutInterval = 5
        
        URLSession.shared.dataTask(with: request) { [weak self] data, response, error in
            DispatchQueue.main.async {
                if let httpResponse = response as? HTTPURLResponse,
                   httpResponse.statusCode == 200 {
                    self?.isConnected = true
                } else {
                    self?.isConnected = false
                }
            }
        }.resume()
    }
    
    func triggerSync(skipSync: Bool = false, syncOnly: Bool = false, allMonths: Bool = false) {
        guard let url = URL(string: "\(baseURL)/sync") else { return }
        
        isLoading = true
        currentTask = nil
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        let body: [String: Any] = [
            "skip_sync": skipSync,
            "sync_only": syncOnly,
            "all_months": allMonths
        ]
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)
        
        URLSession.shared.dataTask(with: request) { [weak self] data, response, error in
            DispatchQueue.main.async {
                if let data = data,
                   let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                   let taskId = json["task_id"] as? String {
                    self?.startPolling(taskId: taskId)
                } else {
                    self?.isLoading = false
                }
            }
        }.resume()
    }
    
    func triggerAnalysis() {
        guard let url = URL(string: "\(baseURL)/analysis") else { return }
        
        isLoading = true
        currentTask = nil
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        URLSession.shared.dataTask(with: request) { [weak self] data, response, error in
            DispatchQueue.main.async {
                if let data = data,
                   let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                   let taskId = json["task_id"] as? String {
                    self?.startPolling(taskId: taskId)
                } else {
                    self?.isLoading = false
                }
            }
        }.resume()
    }
    
    private func startPolling(taskId: String) {
        pollingTimer?.invalidate()
        
        // Poll immediately
        pollTaskStatus(taskId: taskId)
        
        // Then poll every 2 seconds
        pollingTimer = Timer.scheduledTimer(withTimeInterval: 2.0, repeats: true) { [weak self] _ in
            self?.pollTaskStatus(taskId: taskId)
        }
    }
    
    private func pollTaskStatus(taskId: String) {
        guard let url = URL(string: "\(baseURL)/status/\(taskId)") else { return }
        
        URLSession.shared.dataTask(with: URLRequest(url: url)) { [weak self] data, response, error in
            guard let data = data,
                  let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
                return
            }
            
            DispatchQueue.main.async {
                let task = TaskStatus(from: json)
                self?.currentTask = task
                
                if task.status.lowercased() != "running" {
                    self?.isLoading = false
                    self?.pollingTimer?.invalidate()
                    self?.pollingTimer = nil
                }
            }
        }.resume()
    }
}

struct TaskStatus {
    let taskId: String?
    let status: String
    let startedAt: String?
    let completedAt: String?
    let output: [String]
    let stats: AnalysisStats?
    let error: String?
    
    init(from json: [String: Any]) {
        self.taskId = json["task_id"] as? String
        self.status = json["status"] as? String ?? "unknown"
        self.startedAt = json["started_at"] as? String
        self.completedAt = json["completed_at"] as? String
        
        if let outputArray = json["output"] as? [String] {
            self.output = outputArray
        } else {
            self.output = []
        }
        
        if let statsDict = json["stats"] as? [String: Any] {
            self.stats = AnalysisStats(from: statsDict)
        } else {
            self.stats = nil
        }
        
        self.error = json["error"] as? String
    }
}

struct AnalysisStats {
    let totalTracks: Int
    let totalArtists: Int
    let totalPlaylists: Int
    let totalHours: Double
    let avgPopularity: Double
    
    init(from json: [String: Any]) {
        self.totalTracks = json["total_tracks"] as? Int ?? 0
        self.totalArtists = json["total_artists"] as? Int ?? 0
        self.totalPlaylists = json["total_playlists"] as? Int ?? 0
        self.totalHours = json["total_hours"] as? Double ?? 0.0
        self.avgPopularity = json["avg_popularity"] as? Double ?? 0.0
    }
}
