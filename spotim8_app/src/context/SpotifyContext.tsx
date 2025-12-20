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

// Local caching - ONLY enabled in development mode for faster iteration
// In production, data is never persisted (privacy-first)
const DEV_CACHE_ENABLED = import.meta.env.DEV
const CACHE_KEY = 'spotim8_dev_cache'
const CACHE_VERSION = 1

interface CachedData {
  version: number
  timestamp: number
  libraryData: analytics.LibraryStats
  genreData: analytics.GenreData[]
  topArtists: analytics.ArtistData[]
  tracks: analytics.TrackData[]
  timelineData: analytics.TimelineData[]
  decadeData: { decade: string; tracks: number }[]
  popularityDistribution: { range: string; count: number }[]
  playlists: spotify.SpotifyPlaylist[]
  hiddenGems: analytics.TrackData[]
}

function saveToCache(data: Omit<CachedData, 'version' | 'timestamp'>): void {
  if (!DEV_CACHE_ENABLED) return
  try {
    const cached: CachedData = {
      ...data,
      version: CACHE_VERSION,
      timestamp: Date.now(),
    }
    localStorage.setItem(CACHE_KEY, JSON.stringify(cached))
    if (import.meta.env.DEV) console.log('💾 Dev cache: Data saved')
  } catch (err) {
    if (import.meta.env.DEV) console.warn('Cache save failed:', err)
  }
}

function loadFromCache(): CachedData | null {
  if (!DEV_CACHE_ENABLED) return null
  try {
    const raw = localStorage.getItem(CACHE_KEY)
    if (!raw) return null
    const cached: CachedData = JSON.parse(raw)
    if (cached.version !== CACHE_VERSION) {
      localStorage.removeItem(CACHE_KEY)
      return null
    }
    return cached
  } catch {
    return null
  }
}

function clearCache(): void {
  localStorage.removeItem(CACHE_KEY)
}

// Local backend data - loads from parquet exports (dev mode only)
// Run: python scripts/export_for_web.py to generate
interface LocalLibraryData {
  playlists: spotify.SpotifyPlaylist[]
  tracks: spotify.SpotifyTrack[]
  trackPlaylistMap: Record<string, string[]>
  artists: Record<string, spotify.SpotifyArtist>
  exportedAt: string
}

async function loadLocalBackendData(): Promise<LocalLibraryData | null> {
  if (!import.meta.env.DEV) return null
  
  try {
    const response = await fetch('/spotim8/dev-data/library.json')
    if (!response.ok) return null
    return await response.json()
  } catch {
    return null
  }
}

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
  
  // Cache info (dev only)
  isCached: boolean
  dataSource: 'api' | 'cache' | 'local' | null  // Where data came from
  
  // Actions
  login: () => Promise<void>
  logout: () => void
  loadData: () => Promise<void>
  refreshData: () => Promise<void>  // Force refresh, ignore cache
  loadFromBackend: () => Promise<void>  // Load from local parquet exports (dev only)
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
  const [isCached, setIsCached] = useState(false)
  const [dataSource, setDataSource] = useState<'api' | 'cache' | 'local' | null>(null)
  
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
} catch {
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
  
  const loadData = useCallback(async (forceRefresh = false) => {
    if (!isAuthenticated) return
    
    // Check cache first (dev mode only)
    if (!forceRefresh && DEV_CACHE_ENABLED) {
      const cached = loadFromCache()
      if (cached) {
        setLibraryData(cached.libraryData)
        setGenreData(cached.genreData)
        setTopArtists(cached.topArtists)
        setTracks(cached.tracks)
        setTimelineData(cached.timelineData)
        setDecadeData(cached.decadeData)
        setPopularityDistribution(cached.popularityDistribution)
        setPlaylists(cached.playlists)
        setHiddenGems(cached.hiddenGems)
        setIsCached(true)
        setDataSource('cache')
        return
      }
    }
    
    setIsCached(false)
    setDataSource('api')
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
      
      // Fetch tracks from playlists in parallel (limit to first 15 playlists, 5 concurrent)
      const playlistsToFetch = userPlaylists.slice(0, 15)
      const CONCURRENCY = 5
      let completed = 0
      
      // Process playlists in parallel batches
      const processPlaylist = async (playlist: spotify.SpotifyPlaylist) => {
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
        } catch {
          // Skip failed playlists
        }
        completed++
        setLoadingProgress({ 
          stage: `Loading playlists (${completed}/${playlistsToFetch.length})...`, 
          progress: 20 + (completed / playlistsToFetch.length) * 40 
        })
      }
      
      // Process in batches of CONCURRENCY
      for (let i = 0; i < playlistsToFetch.length; i += CONCURRENCY) {
        const batch = playlistsToFetch.slice(i, i + CONCURRENCY)
        await Promise.all(batch.map(processPlaylist))
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
      } catch {
        // Continue without liked songs
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
      
      // Save to cache (dev mode only)
      if (DEV_CACHE_ENABLED) {
        saveToCache({
          libraryData: processed.stats,
          genreData: processed.genreData,
          topArtists: processed.topArtists,
          tracks: processed.tracks,
          timelineData: processed.timelineData,
          decadeData: processed.decadeData,
          popularityDistribution: processed.popularityDistribution,
          playlists: userPlaylists,
          hiddenGems: analytics.findHiddenGems(processed.tracks),
        })
      }
    } catch {
      setLoadingProgress({ stage: 'Error loading data', progress: 0 })
    } finally {
      setIsDataLoading(false)
    }
  }, [isAuthenticated])
  
  // Force refresh data (clears cache and reloads)
  const refreshData = useCallback(async () => {
    if (DEV_CACHE_ENABLED) {
      clearCache()
    }
    setDataSource(null)
    await loadData(true)
  }, [loadData])
  
  // Load from local backend parquet exports (dev only)
  const loadFromBackend = useCallback(async () => {
    if (!import.meta.env.DEV) return
    
    setIsDataLoading(true)
    setLoadingProgress({ stage: 'Loading from local backend...', progress: 10 })
    
    try {
      const localData = await loadLocalBackendData()
      if (!localData) {
        setLoadingProgress({ stage: 'No local data found. Run: python scripts/export_for_web.py', progress: 0 })
        setIsDataLoading(false)
        return
      }
      
      setLoadingProgress({ stage: 'Processing local data...', progress: 50 })
      
      // Build track map from local data
      const allTracks = new Map<string, { track: spotify.SpotifyTrack; playlistIds: Set<string> }>()
      const artistGenres = new Map<string, string[]>()
      
      // Add artist genres
      Object.values(localData.artists).forEach((artist) => {
        artistGenres.set(artist.id, artist.genres)
      })
      
      // Build track map with playlist associations
      localData.tracks.forEach((track) => {
        const playlistIds = new Set(localData.trackPlaylistMap[track.id] || [])
        allTracks.set(track.id, { track, playlistIds })
      })
      
      setLoadingProgress({ stage: 'Generating analytics...', progress: 80 })
      
      // Process analytics with full genre data
      const processed = analytics.processLibraryData(localData.playlists, allTracks, artistGenres)
      
      setPlaylists(localData.playlists)
      setLibraryData(processed.stats)
      setGenreData(processed.genreData)
      setTopArtists(processed.topArtists)
      setTracks(processed.tracks)
      setTimelineData(processed.timelineData)
      setDecadeData(processed.decadeData)
      setPopularityDistribution(processed.popularityDistribution)
      setHiddenGems(analytics.findHiddenGems(processed.tracks))
      setDataSource('local')
      setIsCached(false)
      
      setLoadingProgress({ stage: 'Done! Loaded from local backend.', progress: 100 })
    } catch {
      setLoadingProgress({ stage: 'Error loading local data', progress: 0 })
    } finally {
      setIsDataLoading(false)
    }
  }, [])
  
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
      } catch {
        // Genre loading failed, continue with existing data
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
      isCached,
      dataSource,
      login,
      logout,
      loadData,
      refreshData,
      loadFromBackend,
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

