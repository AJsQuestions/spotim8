/**
 * Spotify Web API Client with PKCE OAuth
 * 
 * ⚠️ PRIVACY: All authentication and data processing happens entirely in your browser.
 * No data is ever sent to or stored on any server. This is a purely client-side application.
 */

// Spotify API endpoints
const SPOTIFY_AUTH_URL = 'https://accounts.spotify.com/authorize'
const SPOTIFY_TOKEN_URL = 'https://accounts.spotify.com/api/token'
const SPOTIFY_API_BASE = 'https://api.spotify.com/v1'

// OAuth Configuration
// For GitHub Pages, use your deployed URL
const getRedirectUri = () => {
  if (typeof window !== 'undefined') {
    const { protocol, host } = window.location
    // Handle both local dev and production
    const basePath = import.meta.env.BASE_URL || '/'
    return `${protocol}//${host}${basePath}`
  }
  return ''
}

// Scopes needed for reading library data
const SCOPES = [
  'user-read-private',
  'user-read-email',
  'user-library-read',
  'playlist-read-private',
  'playlist-read-collaborative',
  'user-top-read',
].join(' ')

// PKCE Helper Functions
function generateRandomString(length: number): string {
  const possible = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
  const values = crypto.getRandomValues(new Uint8Array(length))
  return Array.from(values).map(x => possible[x % possible.length]).join('')
}

async function sha256(plain: string): Promise<ArrayBuffer> {
  const encoder = new TextEncoder()
  const data = encoder.encode(plain)
  return crypto.subtle.digest('SHA-256', data)
}

function base64urlencode(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer)
  let str = ''
  bytes.forEach(byte => str += String.fromCharCode(byte))
  return btoa(str).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

async function generateCodeChallenge(verifier: string): Promise<string> {
  const hashed = await sha256(verifier)
  return base64urlencode(hashed)
}

// Auth State Management (stored in sessionStorage, cleared on tab close)
export function getAccessToken(): string | null {
  return sessionStorage.getItem('spotify_access_token')
}

export function setAccessToken(token: string, expiresIn: number): void {
  sessionStorage.setItem('spotify_access_token', token)
  sessionStorage.setItem('spotify_token_expiry', String(Date.now() + expiresIn * 1000))
}

export function clearAuth(): void {
  sessionStorage.removeItem('spotify_access_token')
  sessionStorage.removeItem('spotify_token_expiry')
  sessionStorage.removeItem('spotify_code_verifier')
}

export function isTokenExpired(): boolean {
  const expiry = sessionStorage.getItem('spotify_token_expiry')
  if (!expiry) return true
  return Date.now() > parseInt(expiry)
}

export function isAuthenticated(): boolean {
  return !!getAccessToken() && !isTokenExpired()
}

// OAuth Flow
export async function initiateLogin(clientId: string): Promise<void> {
  const codeVerifier = generateRandomString(64)
  sessionStorage.setItem('spotify_code_verifier', codeVerifier)
  
  const codeChallenge = await generateCodeChallenge(codeVerifier)
  
  const params = new URLSearchParams({
    client_id: clientId,
    response_type: 'code',
    redirect_uri: getRedirectUri(),
    scope: SCOPES,
    code_challenge_method: 'S256',
    code_challenge: codeChallenge,
    state: generateRandomString(16),
  })
  
  window.location.href = `${SPOTIFY_AUTH_URL}?${params.toString()}`
}

export async function handleCallback(clientId: string): Promise<boolean> {
  const params = new URLSearchParams(window.location.search)
  const code = params.get('code')
  const error = params.get('error')
  
  if (error) {
    console.error('OAuth error:', error)
    return false
  }
  
  if (!code) {
    return false
  }
  
  const codeVerifier = sessionStorage.getItem('spotify_code_verifier')
  if (!codeVerifier) {
    console.error('No code verifier found')
    return false
  }
  
  try {
    const response = await fetch(SPOTIFY_TOKEN_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: new URLSearchParams({
        client_id: clientId,
        grant_type: 'authorization_code',
        code,
        redirect_uri: getRedirectUri(),
        code_verifier: codeVerifier,
      }),
    })
    
    if (!response.ok) {
      throw new Error('Token exchange failed')
    }
    
    const data = await response.json()
    setAccessToken(data.access_token, data.expires_in)
    
    // Clean up URL
    window.history.replaceState({}, document.title, window.location.pathname)
    
    return true
  } catch (error) {
    console.error('Token exchange error:', error)
    return false
  }
}

// API Fetching
async function fetchSpotify<T>(endpoint: string): Promise<T> {
  const token = getAccessToken()
  if (!token) throw new Error('Not authenticated')
  
  const response = await fetch(`${SPOTIFY_API_BASE}${endpoint}`, {
    headers: {
      'Authorization': `Bearer ${token}`,
    },
  })
  
  if (response.status === 401) {
    clearAuth()
    throw new Error('Token expired')
  }
  
  if (!response.ok) {
    throw new Error(`API error: ${response.status}`)
  }
  
  return response.json()
}

// Fetch all pages of a paginated endpoint
async function fetchAllPages<T>(endpoint: string, pageLimit = 50, maxItems?: number): Promise<T[]> {
  const items: T[] = []
  let offset = 0
  let hasMore = true
  
  while (hasMore) {
    const separator = endpoint.includes('?') ? '&' : '?'
    const data: any = await fetchSpotify(`${endpoint}${separator}limit=${pageLimit}&offset=${offset}`)
    
    if (data.items) {
      items.push(...data.items)
      hasMore = data.next !== null
      offset += pageLimit
      
      // Stop if we've reached the max items limit
      if (maxItems && items.length >= maxItems) {
        hasMore = false
      }
    } else {
      hasMore = false
    }
    
    // Rate limiting protection (reduced for speed)
    await new Promise(resolve => setTimeout(resolve, 50))
  }
  
  return maxItems ? items.slice(0, maxItems) : items
}

// User Profile
export interface SpotifyUser {
  id: string
  display_name: string
  email: string
  images: { url: string }[]
  country: string
  product: string
}

export async function getCurrentUser(): Promise<SpotifyUser> {
  return fetchSpotify('/me')
}

// Playlists
export interface SpotifyPlaylist {
  id: string
  name: string
  description: string
  images: { url: string }[]
  tracks: { total: number }
  owner: { id: string; display_name: string }
  public: boolean
}

export async function getUserPlaylists(): Promise<SpotifyPlaylist[]> {
  return fetchAllPages('/me/playlists')
}

// Playlist Tracks
export interface SpotifyTrack {
  id: string
  name: string
  popularity: number
  duration_ms: number
  album: {
    id: string
    name: string
    release_date: string
    images: { url: string }[]
  }
  artists: {
    id: string
    name: string
  }[]
  external_urls: { spotify: string }
}

export interface PlaylistTrackItem {
  track: SpotifyTrack | null
  added_at: string
}

export async function getPlaylistTracks(playlistId: string): Promise<PlaylistTrackItem[]> {
  return fetchAllPages(`/playlists/${playlistId}/tracks?fields=items(added_at,track(id,name,popularity,duration_ms,album(id,name,release_date,images),artists(id,name),external_urls))`)
}

// Saved/Liked Tracks
export async function getSavedTracks(maxItems?: number): Promise<PlaylistTrackItem[]> {
  return fetchAllPages('/me/tracks', 50, maxItems)
}

// Top Artists and Tracks
export interface SpotifyArtist {
  id: string
  name: string
  genres: string[]
  popularity: number
  followers: { total: number }
  images: { url: string }[]
}

export async function getTopArtists(timeRange: 'short_term' | 'medium_term' | 'long_term' = 'medium_term'): Promise<SpotifyArtist[]> {
  const data: any = await fetchSpotify(`/me/top/artists?time_range=${timeRange}&limit=50`)
  return data.items
}

export async function getTopTracks(timeRange: 'short_term' | 'medium_term' | 'long_term' = 'medium_term'): Promise<SpotifyTrack[]> {
  const data: any = await fetchSpotify(`/me/top/tracks?time_range=${timeRange}&limit=50`)
  return data.items
}

// Get artist details (for genres)
export async function getArtists(ids: string[]): Promise<SpotifyArtist[]> {
  if (ids.length === 0) return []
  
  const artists: SpotifyArtist[] = []
  // API allows max 50 IDs per request
  for (let i = 0; i < ids.length; i += 50) {
    const batch = ids.slice(i, i + 50)
    const data: any = await fetchSpotify(`/artists?ids=${batch.join(',')}`)
    artists.push(...data.artists.filter(Boolean))
    await new Promise(resolve => setTimeout(resolve, 100))
  }
  
  return artists
}

