/**
 * Spotify Context Provider
 * 
 * ⚠️ PRIVACY NOTICE:
 * - All data is processed entirely in your browser
 * - No data is ever sent to or stored on any server
 * - Your Spotify credentials are handled directly by Spotify's OAuth
 * - Session data is stored only in sessionStorage and cleared when you close the tab
 * - This is an open-source academic project with no data collection
 */

import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react'
import * as spotify from '../lib/spotify'
import * as analytics from '../lib/analytics'

// Your Spotify App Client ID
// Create one at https://developer.spotify.com/dashboard
// Set redirect URI to your GitHub Pages URL
const CLIENT_ID = import.meta.env.VITE_SPOTIFY_CLIENT_ID || ''

interface SpotifyContextType {
  // Auth state
  isAuthenticated: boolean
  isLoading: boolean
  user: spotify.SpotifyUser | null
  
  // Data state
  isDataLoading: boolean
  isLoadingGenres: boolean
  loadingProgress: { stage: string; progress: number }
  libraryData: analytics.LibraryStats | null
  genreData: analytics.GenreData[]
  topArtists: analytics.ArtistData[]
  tracks: analytics.TrackData[]
  timelineData: analytics.TimelineData[]
  decadeData: { decade: string; tracks: number }[]
  popularityDistribution: { range: string; count: number }[]
  playlists: spotify.SpotifyPlaylist[]
  hiddenGems: analytics.TrackData[]
  
  // Actions
  login: () => Promise<void>
  logout: () => void
  loadData: () => Promise<void>
}

const SpotifyContext = createContext<SpotifyContextType | null>(null)

export function SpotifyProvider({ children }: { children: ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [user, setUser] = useState<spotify.SpotifyUser | null>(null)
  
  const [isDataLoading, setIsDataLoading] = useState(false)
  const [isLoadingGenres, setIsLoadingGenres] = useState(false)
  const [loadingProgress, setLoadingProgress] = useState({ stage: '', progress: 0 })
  
  // Store artist IDs and track map for lazy genre loading
  const [pendingArtistIds, setPendingArtistIds] = useState<Set<string>>(new Set())
  const [cachedTrackMap, setCachedTrackMap] = useState<Map<string, { track: spotify.SpotifyTrack; playlistIds: Set<string> }> | null>(null)
  
  const [libraryData, setLibraryData] = useState<analytics.LibraryStats | null>(null)
  const [genreData, setGenreData] = useState<analytics.GenreData[]>([])
  const [topArtists, setTopArtists] = useState<analytics.ArtistData[]>([])
  const [tracks, setTracks] = useState<analytics.TrackData[]>([])
  const [timelineData, setTimelineData] = useState<analytics.TimelineData[]>([])
  const [decadeData, setDecadeData] = useState<{ decade: string; tracks: number }[]>([])
  const [popularityDistribution, setPopularityDistribution] = useState<{ range: string; count: number }[]>([])
  const [playlists, setPlaylists] = useState<spotify.SpotifyPlaylist[]>([])
  const [hiddenGems, setHiddenGems] = useState<analytics.TrackData[]>([])
  
  // Check auth on mount and handle OAuth callback
  useEffect(() => {
    async function checkAuth() {
      // Handle OAuth callback
      if (window.location.search.includes('code=')) {
        const success = await spotify.handleCallback(CLIENT_ID)
        if (success) {
          setIsAuthenticated(true)
        }
      } else if (spotify.isAuthenticated()) {
        setIsAuthenticated(true)
      }
      setIsLoading(false)
    }
    
    checkAuth()
  }, [])
  
  // Fetch user profile when authenticated
  useEffect(() => {
    async function fetchUser() {
      if (isAuthenticated) {
        try {
          const userData = await spotify.getCurrentUser()
          setUser(userData)
        } catch (error) {
          console.error('Failed to fetch user:', error)
          logout()
        }
      }
    }
    
    fetchUser()
  }, [isAuthenticated])
  
  const login = useCallback(async () => {
    if (!CLIENT_ID) {
      alert('Please set VITE_SPOTIFY_CLIENT_ID in your environment variables')
      return
    }
    await spotify.initiateLogin(CLIENT_ID)
  }, [])
  
  const logout = useCallback(() => {
    spotify.clearAuth()
    setIsAuthenticated(false)
    setUser(null)
    setLibraryData(null)
    setGenreData([])
    setTopArtists([])
    setTracks([])
    setTimelineData([])
    setDecadeData([])
    setPopularityDistribution([])
    setPlaylists([])
    setHiddenGems([])
  }, [])
  
  const loadData = useCallback(async () => {
    if (!isAuthenticated) return
    
    setIsDataLoading(true)
    setLoadingProgress({ stage: 'Fetching playlists...', progress: 10 })
    
    try {
      // Fetch playlists
      const userPlaylists = await spotify.getUserPlaylists()
      setPlaylists(userPlaylists)
      setLoadingProgress({ stage: 'Loading tracks...', progress: 20 })
      
      // Track map: trackId -> { track, playlistIds }
      const allTracks = new Map<string, { track: spotify.SpotifyTrack; playlistIds: Set<string> }>()
      const artistIds = new Set<string>()
      
      // Fetch tracks from each playlist (limit to first 20 playlists for speed)
      const playlistsToFetch = userPlaylists.slice(0, 20)
      for (let i = 0; i < playlistsToFetch.length; i++) {
        const playlist = playlistsToFetch[i]
        setLoadingProgress({ 
          stage: `Loading ${playlist.name}...`, 
          progress: 20 + (i / playlistsToFetch.length) * 40 
        })
        
        try {
          const trackItems = await spotify.getPlaylistTracks(playlist.id)
          trackItems.forEach((item: spotify.PlaylistTrackItem) => {
            if (item.track && item.track.id) {
              const existing = allTracks.get(item.track.id)
              if (existing) {
                existing.playlistIds.add(playlist.id)
              } else {
                allTracks.set(item.track.id, {
                  track: item.track,
                  playlistIds: new Set([playlist.id]),
                })
              }
              item.track.artists.forEach((a: { id: string; name: string }) => artistIds.add(a.id))
            }
          })
        } catch (err) {
          console.warn(`Failed to load playlist ${playlist.name}:`, err)
        }
      }
      
      // Fetch liked songs (limit to 200 for speed)
      setLoadingProgress({ stage: 'Loading liked songs...', progress: 70 })
      try {
        const likedTracks = await spotify.getSavedTracks(200) // Limit for speed
        likedTracks.forEach((item: spotify.PlaylistTrackItem) => {
          if (item.track && item.track.id) {
            const existing = allTracks.get(item.track.id)
            if (existing) {
              existing.playlistIds.add('__liked__')
            } else {
              allTracks.set(item.track.id, {
                track: item.track,
                playlistIds: new Set(['__liked__']),
              })
            }
            item.track.artists.forEach((a: { id: string; name: string }) => artistIds.add(a.id))
          }
        })
      } catch (err) {
        console.warn('Failed to load liked songs:', err)
      }
      
      // Skip artist genres initially for faster load - use empty map
      // Genres will show as "Other" until lazy-loaded in background
      const artistGenres = new Map<string, string[]>()
      
      // Process analytics immediately (without genre data)
      setLoadingProgress({ stage: 'Processing analytics...', progress: 90 })
      const processed = analytics.processLibraryData(userPlaylists, allTracks, artistGenres)
      
      setLibraryData(processed.stats)
      setGenreData(processed.genreData)
      setTopArtists(processed.topArtists)
      setTracks(processed.tracks)
      setTimelineData(processed.timelineData)
      setDecadeData(processed.decadeData)
      setPopularityDistribution(processed.popularityDistribution)
      setHiddenGems(analytics.findHiddenGems(processed.tracks))
      
      // Save for lazy genre loading
      setPendingArtistIds(artistIds)
      setCachedTrackMap(allTracks)
      
      setLoadingProgress({ stage: 'Done! Loading genres in background...', progress: 100 })
    } catch (error) {
      console.error('Failed to load data:', error)
      setLoadingProgress({ stage: 'Error loading data', progress: 0 })
    } finally {
      setIsDataLoading(false)
    }
  }, [isAuthenticated])
  
  // Lazy load genres in background after initial data load
  useEffect(() => {
    async function loadGenresInBackground() {
      if (pendingArtistIds.size === 0 || !cachedTrackMap || !playlists.length) return
      
      setIsLoadingGenres(true)
      
      try {
        const artistGenres = new Map<string, string[]>()
        const artists = await spotify.getArtists(Array.from(pendingArtistIds))
        artists.forEach((artist: spotify.SpotifyArtist | null) => {
          if (artist) {
            artistGenres.set(artist.id, artist.genres)
          }
        })
        
        // Re-process analytics with genre data
        const processed = analytics.processLibraryData(playlists, cachedTrackMap, artistGenres)
        
        setGenreData(processed.genreData)
        setTopArtists(processed.topArtists)
        setTracks(processed.tracks)
        setTimelineData(processed.timelineData)
        setHiddenGems(analytics.findHiddenGems(processed.tracks))
        
        // Clear pending data
        setPendingArtistIds(new Set())
        setCachedTrackMap(null)
      } catch (err) {
        console.warn('Failed to load genres in background:', err)
      } finally {
        setIsLoadingGenres(false)
      }
    }
    
    // Start loading genres after a short delay to let UI render first
    const timer = setTimeout(loadGenresInBackground, 500)
    return () => clearTimeout(timer)
  }, [pendingArtistIds, cachedTrackMap, playlists])
  
  return (
    <SpotifyContext.Provider value={{
      isAuthenticated,
      isLoading,
      user,
      isDataLoading,
      isLoadingGenres,
      loadingProgress,
      libraryData,
      genreData,
      topArtists,
      tracks,
      timelineData,
      decadeData,
      popularityDistribution,
      playlists,
      hiddenGems,
      login,
      logout,
      loadData,
    }}>
      {children}
    </SpotifyContext.Provider>
  )
}

export function useSpotify() {
  const context = useContext(SpotifyContext)
  if (!context) {
    throw new Error('useSpotify must be used within a SpotifyProvider')
  }
  return context
}

