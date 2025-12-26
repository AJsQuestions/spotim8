//
//  MainView.swift
//  Spotim8
//
//  Main tab-based view
//

import SwiftUI

struct MainView: View {
    @State private var selectedTab = 0
    
    var body: some View {
        TabView(selection: $selectedTab) {
            LibraryView()
                .tabItem {
                    Label("Library", systemImage: "music.note.list")
                }
                .tag(0)
            
            AutomationView()
                .tabItem {
                    Label("Automation", systemImage: "gearshape.2")
                }
                .tag(1)
        }
    }
}
