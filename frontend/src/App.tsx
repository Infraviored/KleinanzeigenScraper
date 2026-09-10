/* eslint-disable react-hooks/set-state-in-effect */
import { useState, useEffect, useCallback } from 'react'
import type { Campaign, KnowledgeSet, SearchTarget, Listing, SampleListing } from './types'
import ScraperProgressCard from './components/ScraperProgressCard'
import PlaceInput from './components/PlaceInput'
import type { Place } from './components/PlaceInput'
import ListingDetailCard from './components/ListingDetailCard'
import GuidelinesWizard from './components/GuidelinesWizard'
import SettingsView from './components/SettingsView'
import { transformListing } from './utils/listingTransformer'
import { useHashRouter } from './hooks/useHashRouter'
import { Menu, X, Settings, Globe, LogOut, Key, Search, RefreshCw, Sparkles, ChevronDown } from 'lucide-react'
import { useTranslation } from './hooks/useTranslation'
import { Button } from './components/ui/Button'
import { Input } from './components/ui/Input'
import { Card } from './components/ui/Card'
import { Select } from './components/ui/Select'
import { cn } from './utils/cn'



const isValidKleinanzeigenUrl = (urlStr: string): boolean => {
  try {
    const url = new URL(urlStr);
    return url.hostname.includes('kleinanzeigen.de');
  } catch {
    return false;
  }
};

const suggestTitleFromUrl = (urlStr: string): string => {
  try {
    const url = new URL(urlStr);
    const paths = url.pathname.split('/');
    const candidate = paths.find(segment => {
      if (!segment) return false;
      if (segment.startsWith('s-')) return false;
      if (segment.includes(':')) return false;
      if (/^\d+$/.test(segment)) return false;
      if (segment.startsWith('k0') || segment.includes('+') || segment.includes('.')) return false;
      if (['suche', 'kategorie', 'anzeigen'].includes(segment.toLowerCase())) return false;
      return true;
    });
    
    if (candidate) {
      return decodeURIComponent(candidate)
        .replace(/-/g, ' ')
        .trim();
    }
  } catch {
    // Ignore
  }
  return '';
};




export default function App() {
  const {
    view,
    currentCampaignId,
    currentSearchId,
    selectedListingId,
    wizardStep,
    previousView,
    setView,
    setCurrentCampaignId,
    setCurrentSearchId,
    setSelectedListingId,
    setWizardStep,
    navigate
  } = useHashRouter()

  const { t, lang, toggleLanguage } = useTranslation()

  const [isRegisteringTarget, setIsRegisteringTarget] = useState(false)
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false)
  const [isLangDropdownOpen, setIsLangDropdownOpen] = useState(false)

  // Database lists
  const [campaigns, setCampaigns] = useState<Campaign[]>([])
  const [searches, setSearches] = useState<SearchTarget[]>([])
  const [listings, setListings] = useState<Listing[]>([])
  const [knowledgeSets, setKnowledgeSets] = useState<KnowledgeSet[]>([])

  // Authentication session state
  const [sessionEmail, setSessionEmail] = useState<string | null>(null)
  const [appUser, setAppUser] = useState<{ email: string, role: string } | null>(null)
  const [authLoading, setAuthLoading] = useState(true)
  const [loginEmail, setLoginEmail] = useState('')
  const [loginPassword, setLoginPassword] = useState('')
  const [loginError, setLoginError] = useState('')
  const [isLoggingIn, setIsLoggingIn] = useState(false)

  // Sidebar selections & details
  const [currentKnowledgeSetId, setCurrentKnowledgeSetId] = useState<number | null>(null)

  const activeSearches = searches.filter(s => s.campaign_id === currentCampaignId)
  const activeSearchTarget = searches.find(s => s.id === currentSearchId) || activeSearches[0]


  // Filtering states for Deal Matcher
  const [selectedSearchId, setSelectedSearchId] = useState<string>('All')
  const [selectedStatusFilter, setSelectedStatusFilter] = useState<'All' | 'High Niceness' | 'New' | 'Evaluate with AI'>('All')
  const [activeProcessingListingIds, setActiveProcessingListingIds] = useState<string[]>([])

  // Inline forms
  const [newCampaignName, setNewCampaignName] = useState('')
  const [newTargetUrl, setNewTargetUrl] = useState('')
  // Route corridor search. `routeMode` also suppresses the debounced
  // auto-registration below: a corridor is several searches, and registering the
  // pasted URL as a single one the moment it looks valid would quietly give the
  // user the point search they were trying not to make.
  const [routeMode, setRouteMode] = useState(false)
  const [routeFrom, setRouteFrom] = useState<Place | null>(null)
  const [routeTo, setRouteTo] = useState<Place | null>(null)
  const [routeRadiusKm, setRouteRadiusKm] = useState(30)
  const [routeCorridorKm, setRouteCorridorKm] = useState(15)
  const [routePlanning, setRoutePlanning] = useState(false)
  const [routeError, setRouteError] = useState<string | null>(null)
  const [routeResult, setRouteResult] = useState<{ count: number; width: number } | null>(null)
  const [isEditingCampaignName, setIsEditingCampaignName] = useState(false)

  // Step wizard states for Guidelines Editor
  const [sampledListings, setSampledListings] = useState<SampleListing[]>([])
  const [sampledListingsLoading, setSampledListingsLoading] = useState(false)
  const [marketMemo, setMarketMemo] = useState<string>('')
  const [researcherOutput, setResearcherOutput] = useState<string>('')

  // Prompt templates from backend
  const [researchPromptTemplate, setResearchPromptTemplate] = useState<string>('')
  const [marketPromptTemplate, setMarketPromptTemplate] = useState<string>('')
  const [profilePromptTemplate, setProfilePromptTemplate] = useState<string>('')

  // Parsed XML states for Step 3
  const [parsedExpertKnowledge, setParsedExpertKnowledge] = useState('')
  const [parsedGoodRef, setParsedGoodRef] = useState('')
  const [parsedBadRef, setParsedBadRef] = useState('')
  const [parsedDemoMsg, setParsedDemoMsg] = useState('')
  const [parsedItemJson, setParsedItemJson] = useState('')

  // Compatibility names for existing views and components
  const [editKsName, setEditKsName] = useState('')
  const [editKsError, setEditKsError] = useState('')

  const checkAuth = async () => {
    try {
      const res = await fetch('/api/auth/me')
      if (res.ok) {
        const data = await res.json()
        setAppUser(data.user || null)
        return data.user
      } else {
        setAppUser(null)
      }
    } catch (err) {
      console.error("Auth check failed:", err)
      setAppUser(null)
    } finally {
      setAuthLoading(false)
    }
    return null
  }

  const handleLoginSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!loginEmail.trim() || !loginPassword.trim()) {
      setLoginError("Please enter email and password.")
      return
    }
    setIsLoggingIn(true)
    setLoginError('')
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: loginEmail, password: loginPassword })
      })
      const data = await res.json()
      if (res.ok && data.success) {
        setAppUser(data.user)
      } else {
        setLoginError(data.error || t('auth.errorInvalid'))
      }
    } catch {
      setLoginError("Network connection failed.")
    } finally {
      setIsLoggingIn(false)
    }
  }

  const handleLogout = async () => {
    try {
      await fetch('/api/auth/logout', { method: 'POST' })
      setAppUser(null)
    } catch (err) {
      console.error("Logout failed:", err)
    }
  }

  const checkSessionStatus = async () => {
    try {
      const res = await fetch('/api/session-status')
      if (res.ok) {
        const data = await res.json()
        setSessionEmail(data.email || null)
      }
    } catch (err) {
      console.error("Error checking session status:", err)
    }
  }

  const fetchSampleListings = async (searchId: number) => {
    setSampledListingsLoading(true)
    try {
      const response = await fetch(`/api/searches/${searchId}/sample-listings`)
      if (response.ok) {
        const data = await response.json()
        setSampledListings(data)
      } else {
        console.error("Failed to fetch sample listings")
        alert("Failed to fetch sample listings from server.")
      }
    } catch (error) {
      console.error("Error fetching sample listings:", error)
      alert("Error contacting the backend to fetch listings.")
    } finally {
      setSampledListingsLoading(false)
    }
  }

  const refreshAll = () => {
    Promise.all([
      fetch('/api/campaigns').then(res => res.json()),
      fetch('/api/search-urls').then(res => res.json()),
      fetch('/api/listings').then(res => res.json()),
      fetch('/api/knowledge-sets').then(res => res.json())
    ]).then(([campaignsData, searchesData, listingsData, ksData]) => {
      setCampaigns(campaignsData)
      setSearches(searchesData)
      setKnowledgeSets(ksData)

      // Map raw listings to include React UI helper properties
      const mappedListings = listingsData.map((l: Listing) => transformListing(l, searchesData, ksData));

      setListings(mappedListings)

      // Set default campaign selection if none set
      if (campaignsData.length > 0 && currentCampaignId === null) {
        setCurrentCampaignId(campaignsData[0].id);
      }
    }).catch(err => {
      console.error("Error refreshing dashboard state:", err)
    })
  }

  // Load Prompt templates
  useEffect(() => {
    fetch('/api/prompts/research')
      .then(r => r.text())
      .then(setResearchPromptTemplate)
      .catch(err => console.error("Error loading research template:", err))

    fetch('/api/prompts/market')
      .then(r => r.text())
      .then(setMarketPromptTemplate)
      .catch(err => console.error("Error loading market template:", err))

    fetch('/api/prompts/profile')
      .then(r => r.text())
      .then(setProfilePromptTemplate)
      .catch(err => console.error("Error loading profile template:", err))
  }, [])

  // Parse XML blocks in Step 3 on the fly
  useEffect(() => {
    const ekMatch = researcherOutput.match(/<expert_knowledge>([\s\S]*?)<\/expert_knowledge>/i)
    setParsedExpertKnowledge(ekMatch ? ekMatch[1].trim() : '')

    const grMatch = researcherOutput.match(/<good_reference_description>([\s\S]*?)<\/good_reference_description>/i)
    setParsedGoodRef(grMatch ? grMatch[1].trim() : '')

    const brMatch = researcherOutput.match(/<bad_reference_description>([\s\S]*?)<\/bad_reference_description>/i)
    setParsedBadRef(brMatch ? brMatch[1].trim() : '')

    const dmMatch = researcherOutput.match(/<demo_message>([\s\S]*?)<\/demo_message>/i)
    setParsedDemoMsg(dmMatch ? dmMatch[1].trim() : '')

    const ijMatch = researcherOutput.match(/<item_json>([\s\S]*?)<\/item_json>/i)
    setParsedItemJson(ijMatch ? ijMatch[1].trim() : '')
  }, [researcherOutput])

  // Live URL validation preview
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewCount, setPreviewCount] = useState<number | null>(null)
  const [previewError, setPreviewError] = useState<string | null>(null)

  // General state
  const [isScraping, setIsScraping] = useState(false)
  const [scrapingStatus, setScrapingStatus] = useState('')
  const [scrapingProgress, setScrapingProgress] = useState<{
    phase: string;
    current: number;
    total: number;
    status: string;
  } | null>(null)
  const [liveLogs, setLiveLogs] = useState<string>('')
  const [showLogConsole, setShowLogConsole] = useState(false)

  // Polling loop for active scraping task
  useEffect(() => {
    let intervalId: ReturnType<typeof setInterval> | null = null;

    const checkStatus = async () => {
      try {
        const res = await fetch('/api/scrape/status');
        if (res.ok) {
          const data = await res.json();
          if (data.active) {
            setIsScraping(true);
            setScrapingProgress(data.progress);
            if (data.progress && data.progress.status) {
              setScrapingStatus(data.progress.status);
            }

            // Also fetch live logs
            const logsRes = await fetch('/api/logs');
            if (logsRes.ok) {
              const logsData = await logsRes.json();
              setLiveLogs(logsData.logs || '');
            }
          } else {
            // Scraper is no longer active in backend
            if (isScraping) {
              setIsScraping(false);
              setScrapingProgress(null);
              setScrapingStatus("Scraping completed!");
              refreshAll();
              if (activeSearchTarget?.id) {
                fetchSampleListings(activeSearchTarget.id);
              }
            }
          }
        }
      } catch (e) {
        console.error("Error polling scraper status:", e);
      }
    };

    // Run immediately
    checkStatus();

    // Poll every 1.5 seconds
    intervalId = setInterval(checkStatus, 1500);

    return () => {
      if (intervalId) clearInterval(intervalId);
    };
    
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isScraping, activeSearchTarget?.id]);

  // Polling loop for active AI evaluations
  useEffect(() => {
    let intervalId: ReturnType<typeof setInterval> | null = null;
    const checkActiveProcesses = async () => {
      try {
        const res = await fetch('/api/process/active');
        if (res.ok) {
          const data = await res.json();
          // If the list of active IDs changed, we might want to refresh listings
          // to get the new scores for those that just finished.
          setActiveProcessingListingIds(prev => {
            const finished = prev.filter(id => !data.active.includes(id));
            if (finished.length > 0) {
              refreshAll();
            }
            return data.active;
          });
        }
      } catch {
        // Ignore
      }
    };
    checkActiveProcesses();
    intervalId = setInterval(checkActiveProcesses, 2000);
    return () => clearInterval(intervalId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const [isProcessing, setIsProcessing] = useState(false)
  const [processingStatus, setProcessingStatus] = useState('')



  // Custom states for images and descriptions

  // Initial load
  useEffect(() => {
    checkAuth()
  }, [])

  // Load data when authenticated
  useEffect(() => {
    if (appUser) {
      refreshAll()
      checkSessionStatus()

      const interval = setInterval(checkSessionStatus, 8000)
      return () => clearInterval(interval)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [appUser])

  // Auto-redirect empty campaigns to configuration view
  useEffect(() => {
    if (currentCampaignId && view === 'dashboard') {
      const campaignSearches = searches.filter(s => s.campaign_id === currentCampaignId);
      if (campaignSearches.length === 0) {
        navigate('edit', currentCampaignId, null);
      }
    }
  }, [currentCampaignId, searches, view, navigate]);

  // Trigger a fast crawler scrape directly from the target URL
  async function triggerFastScrape(searchId: number) {
    setIsScraping(true)
    setScrapingStatus("Spawning targeted crawler to fetch market listings...")
    setLiveLogs("Starting targeted Chrome headless scraper session...")
    setScrapingProgress({ phase: 'starting', current: 0, total: 100, status: 'Spawning scraper worker...' })
    try {
      const res = await fetch(`/api/searches/${searchId}/scrape`, { method: 'POST' })
      if (!res.ok) {
        alert("Failed to start targeted scraper.")
        setIsScraping(false)
      }
    } catch {
      alert("Error triggering targeted scraper.")
      setIsScraping(false)
    }
  }

  const handleDeleteCampaign = useCallback(async (
    campaignId: number,
    name: string,
    searchCount: number,
    listingCount: number
  ) => {
    // Name what is about to be lost. "Are you sure?" tells nobody anything, and
    // deleting a campaign takes its searches and everything crawled into them.
    const contents = [
      searchCount ? t('landing.deleteSearches', { count: searchCount }) : null,
      listingCount ? t('landing.deleteListings', { count: listingCount }) : null,
    ].filter(Boolean).join(', ');

    const message = contents
      ? t('landing.deleteConfirmWithContents', { name, contents })
      : t('landing.deleteConfirm', { name });

    if (!window.confirm(message)) return;

    try {
      const res = await fetch(`/api/campaigns/${campaignId}`, { method: 'DELETE' });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        alert(data.error || t('landing.deleteFailed'));
        return;
      }
      refreshAll();
    } catch {
      alert(t('common.connectionIssueFailed'));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handlePlanCorridor = useCallback(async () => {
    if (!newTargetUrl || !isValidKleinanzeigenUrl(newTargetUrl)) {
      setRouteError(t('common.routeNeedsUrl'));
      return;
    }
    if (!routeFrom || !routeTo) {
      setRouteError(t('common.routeNeedsBoth'));
      return;
    }

    setRoutePlanning(true);
    setRouteError(null);
    setRouteResult(null);

    try {
      const suggested = suggestTitleFromUrl(newTargetUrl) || 'New Search';

      // The corridor's searches share one profile, or each circle would be
      // scored against different criteria for the same thing.
      const ksRes = await fetch('/api/knowledge-sets', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: `${suggested} Guidelines`,
          expert_knowledge: '',
          item_json: {}
        })
      });
      const boundKsId = ksRes.ok ? (await ksRes.json()).id : null;

      const res = await fetch('/api/route-searches', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          campaign_id: currentCampaignId,
          base_url: newTargetUrl,
          // The postal code, not the typed text: the user already resolved the
          // ambiguity by choosing from the list, so nothing is left to guess.
          origin: routeFrom.postal_code,
          destination: routeTo.postal_code,
          radius_km: routeRadiusKm,
          corridor_km: routeCorridorKm,
          knowledge_set_id: boundKsId,
          name: `${suggested}: ${routeFrom.name} → ${routeTo.name}`
        })
      });

      const data = await res.json();
      if (!res.ok) {
        setRouteError(data.error || t('common.targetRegistrationFailed'));
        return;
      }

      setRouteResult({
        count: (data.searches || []).length,
        width: (data.corridor_km || routeCorridorKm) * 2
      });
      setNewTargetUrl('');
      setRouteFrom(null);
      setRouteTo(null);
      setIsRegisteringTarget(false);

      if (data.searches && data.searches.length) {
        setCurrentSearchId(data.searches[0].id);
      }
      refreshAll();
    } catch {
      setRouteError(t('common.connectionIssueFailed'));
    } finally {
      setRoutePlanning(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [newTargetUrl, routeFrom, routeTo, routeRadiusKm, routeCorridorKm, currentCampaignId]);

  // Debounced auto-registration and count fetch
  useEffect(() => {
    if (routeMode) {
      // A corridor is registered deliberately, not the moment a URL looks valid.
      return;
    }
    if (!newTargetUrl || !isValidKleinanzeigenUrl(newTargetUrl)) {
      return;
    }

    // Only auto-register if we are in registration mode
    const campaignSearches = searches.filter(s => s.campaign_id === currentCampaignId);
    if (!(campaignSearches.length === 0 || isRegisteringTarget)) {
      return;
    }

    const timer = setTimeout(async () => {
      // Suggest title
      const suggested = suggestTitleFromUrl(newTargetUrl) || 'New Search';

      setPreviewLoading(true);
      setPreviewError(null);
      setPreviewCount(null);

      try {
        // Fetch count in background
        const countRes = await fetch('/api/searches/preview', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url: newTargetUrl })
        });
        let fetchedCount = null;
        if (countRes.ok) {
          const countData = await countRes.json();
          fetchedCount = countData.count;
          setPreviewCount(fetchedCount);
        }

        // Auto-create guidelines profile
        const ksRes = await fetch('/api/knowledge-sets', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name: `${suggested} Guidelines`,
            expert_knowledge: '',
            item_json: {}
          })
        });
        let boundKsId = null;
        if (ksRes.ok) {
          const ksData = await ksRes.json();
          boundKsId = ksData.id;
        }

        // Auto-register Search Query
        const searchRes = await fetch('/api/searches', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            campaign_id: currentCampaignId,
            name: suggested,
            url: newTargetUrl,
            knowledge_set_id: boundKsId
          })
        });

        if (searchRes.ok) {
          const searchData = await searchRes.json();
          // Reset input states
          setNewTargetUrl('');
          setPreviewCount(null);
          setIsRegisteringTarget(false);
          
          // Set newly registered search active
          setCurrentSearchId(searchData.id);
          
          // Trigger the fast crawler crawl
          triggerFastScrape(searchData.id);

          // Force refresh list of campaigns/searches
          refreshAll();
        } else {
          const errData = await searchRes.json();
          setPreviewError(errData.error || "Failed to auto-register search target.");
        }
      } catch {
        setPreviewError("Failed to auto-register search query due to connection issues.");
      } finally {
        setPreviewLoading(false);
      }
    }, 600); // 600ms debounce

    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [newTargetUrl, currentCampaignId, searches, isRegisteringTarget, routeMode]);




  const handleTriggerLogin = async () => {
    setIsScraping(true)
    setScrapingStatus("Opening interactive browser window on your host... Please complete the login form inside the browser window. We will automatically detect when you have successfully logged in.")
    try {
      const res = await fetch('/api/login-session', { method: 'POST' })
      if (res.ok) {
        const data = await res.json()
        if (data.success) {
          setScrapingStatus("Authentication completed successfully!")
          checkSessionStatus()
        } else {
          setScrapingStatus("Session watcher finished or timed out.")
        }
      } else {
        setScrapingStatus("Authentication process failed to trigger.")
      }
    } catch {
      setScrapingStatus("Error connecting to backend server.")
    } finally {
      setIsScraping(false)
    }
  }



  // Auto load active guidelines when active search target changes
  useEffect(() => {
    if (activeSearchTarget && activeSearchTarget.knowledge_set_id) {
      const boundSet = knowledgeSets.find(ks => ks.id === activeSearchTarget.knowledge_set_id)
      if (boundSet) {
        setCurrentKnowledgeSetId(boundSet.id || null)
        setEditKsName(boundSet.name)
        setMarketMemo(boundSet.market_memo || '')
        
        let samples: SampleListing[] = []
        if (boundSet.market_samples_json) {
          try {
            samples = typeof boundSet.market_samples_json === 'string' 
              ? JSON.parse(boundSet.market_samples_json) 
              : boundSet.market_samples_json
          } catch { /* empty */ }
        }
        setSampledListings(samples)

        let raw = ''
        if (boundSet.expert_knowledge) {
          raw += `<expert_knowledge>\n${boundSet.expert_knowledge}\n</expert_knowledge>\n\n`
        }
        if (boundSet.good_reference_description) {
          raw += `<good_reference_description>\n${boundSet.good_reference_description}\n</good_reference_description>\n\n`
        }
        if (boundSet.bad_reference_description) {
          raw += `<bad_reference_description>\n${boundSet.bad_reference_description}\n</bad_reference_description>\n\n`
        }
        if (boundSet.item_json) {
          const ijStr = typeof boundSet.item_json === 'string' ? boundSet.item_json : JSON.stringify(boundSet.item_json, null, 2)
          raw += `<item_json>\n${ijStr}\n</item_json>`
        }
        setResearcherOutput(raw.trim())
        setEditKsError('')

        // Intelligent step steering: start on the step where they need to make progress
        if (boundSet.market_memo && boundSet.good_reference_description) {
          setWizardStep(3)
        } else if (boundSet.market_memo) {
          setWizardStep(2)
        } else {
          setWizardStep(1)
        }
      }
    } else {
      setCurrentKnowledgeSetId(null)
      setEditKsName('')
      setMarketMemo('')
      setSampledListings([])
      setResearcherOutput('')
      setEditKsError('')
      setWizardStep(1)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeSearchTarget, searches, knowledgeSets])

  // Create Campaign
  const handleCreateCampaign = async (): Promise<number | null> => {
    if (!newCampaignName.trim()) return null
    try {
      const res = await fetch('/api/campaigns', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newCampaignName })
      })
      const data = await res.json()
      if (res.ok) {
        setNewCampaignName('')
        refreshAll()
        return data.id
      } else {
        alert(data.error || "Failed to create campaign.")
      }
    } catch {
      alert("Failed to connect to backend server.")
    }
    return null
  }

  const handleUpdateCampaignName = async (name: string) => {
    if (!currentCampaignId) return
    const previous = campaigns.find(c => c.id === currentCampaignId)?.name
    setCampaigns(prev => prev.map(c => c.id === currentCampaignId ? { ...c, name } : c))
    try {
      const res = await fetch('/api/campaigns', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: currentCampaignId, name })
      })
      if (!res.ok) {
        // The rename was shown before it was saved. Leaving it on screen after
        // the save failed would tell the user the campaign is called something
        // it is not — so put the old name back and say what happened.
        const data = await res.json().catch(() => ({}))
        setCampaigns(prev => prev.map(c =>
          c.id === currentCampaignId && previous ? { ...c, name: previous } : c
        ))
        alert(data.error || t('landing.renameFailed'))
      }
    } catch {
      setCampaigns(prev => prev.map(c =>
        c.id === currentCampaignId && previous ? { ...c, name: previous } : c
      ))
      alert(t('common.connectionIssueFailed'))
    }
  }



  // Trigger AI agent processing on a single specific listing
  const handleProcessSingleListing = async (listingId: string) => {
    // Optimistically add to active list
    setActiveProcessingListingIds(prev => Array.from(new Set([...prev, listingId])))
    try {
      const res = await fetch('/api/process', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ listing_id: listingId })
      })
      if (!res.ok && res.status !== 409) {
        alert("Failed to run AI agent for this listing.")
        setActiveProcessingListingIds(prev => prev.filter(id => id !== listingId))
      }
    } catch {
      alert("Error contacting backend AI worker.")
      setActiveProcessingListingIds(prev => prev.filter(id => id !== listingId))
    }
  }



  // Save Knowledge Set
  const handleSaveKnowledgeSet = async () => {
    if (!editKsName.trim()) {
      alert("Please enter a name for the Guidelines Profile.")
      return
    }

    let parsedJson: Record<string, unknown> = {}
    if (parsedItemJson.trim()) {
      try {
        parsedJson = JSON.parse(parsedItemJson)
      } catch (e) {
        setEditKsError(`Invalid JSON syntax in <item_json>: ${(e as Error).message}`)
        return
      }
    }

    // Verify boolean-only schema check
    const criteria = (parsedJson.extraction_criteria as { id: string; type: string }[]) || []
    for (const c of criteria) {
      if (c.type !== 'boolean') {
        setEditKsError(`Criteria types must be boolean only. Criterion '${c.id}' has type '${c.type}'. Legacy/mixed schemas are not supported in the new pipeline.`)
        return
      }
    }

    try {
      const res = await fetch('/api/knowledge-sets', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          id: currentKnowledgeSetId || undefined,
          name: editKsName,
          expert_knowledge: parsedExpertKnowledge,
          item_json: parsedJson,
          market_memo: marketMemo,
          good_reference_description: parsedGoodRef,
          bad_reference_description: parsedBadRef,
          market_samples_json: JSON.stringify(sampledListings),
          source_search_url: activeSearchTarget?.url || '',
          sample_timestamp: new Date().toISOString()
        })
      })
      if (res.ok) {
        setEditKsError('')
        refreshAll()
        setView('dashboard')
      } else {
        const data = await res.json()
        setEditKsError(data.error || "Failed to save guidelines profile.")
      }
    } catch {
      setEditKsError("Connection to backend server failed.")
    }
  }

  // Trigger crawler background process (Scrape only)
  const handleStartScrape = async () => {
    setIsScraping(true)
    setScrapingStatus("Spawning scraper worker...")
    setLiveLogs("Initializing browser context and logging session...")
    setScrapingProgress({ phase: 'starting', current: 0, total: 100, status: 'Spawning scraper worker...' })
    try {
      const res = await fetch('/api/scrape', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ campaignId: currentCampaignId })
      })
      if (!res.ok) {
        alert("Failed to start scraper.")
        setIsScraping(false)
      }
    } catch {
      alert("Error triggering scraper process.")
      setIsScraping(false)
    }
  }

  // Trigger deep description updates for all existing listings
  const handleStartDeepUpdate = async () => {
    setIsScraping(true)
    setScrapingStatus("Spawning deep update worker...")
    setLiveLogs("Initializing browser context for deep listing harvesting...")
    setScrapingProgress({ phase: 'starting', current: 0, total: 100, status: 'Spawning deep update worker...' })
    try {
      const res = await fetch('/api/scrape/update-all', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ campaignId: currentCampaignId })
      })
      if (!res.ok) {
        alert("Failed to start deep update.")
        setIsScraping(false)
      }
    } catch {
      alert("Error triggering deep update process.")
      setIsScraping(false)
    }
  }

  // Trigger AI Matching Process
  const handleStartProcess = async () => {
    setIsProcessing(true)
    setProcessingStatus("Launching AI Matcher checklist evaluation and deal scoring...")
    try {
      const res = await fetch('/api/process', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ campaignId: currentCampaignId })
      })
      if (res.ok) {
        setProcessingStatus("AI matching completed! Updating Deal Matcher results...")
        setTimeout(() => {
          refreshAll()
          setIsProcessing(false)
        }, 4000)
      } else {
        alert("Failed to launch AI Matcher.")
        setIsProcessing(false)
      }
    } catch {
      alert("Error contacting AI Matching backend.")
      setIsProcessing(false)
    }
  }






  // Filter listings based on currentCampaignId
  const filteredListings = listings.filter(l => {
    const targetSearch = searches.find(s => s.id === l.search_id)
    const matchesCampaign = !currentCampaignId || (targetSearch && targetSearch.campaign_id === currentCampaignId)
    const matchesSearch = selectedSearchId === 'All' || String(l.search_id) === selectedSearchId
    const isMatched = matchesCampaign && matchesSearch

    if (selectedStatusFilter === 'High Niceness') {
      return isMatched && l.llm_processed && l.niceness_score !== null && l.niceness_score !== undefined && l.niceness_score >= 70
    }
    if (selectedStatusFilter === 'New') {
      return isMatched && l.status === 'New'
    }
    if (selectedStatusFilter === 'Evaluate with AI') {
      return isMatched && !l.llm_processed
    }
    return isMatched
  })



  if (authLoading) {
    return (
      <div className="min-h-screen bg-brand-primary flex items-center justify-center font-sans">
        <div className="text-center space-y-4">
          <div className="animate-spin w-8 h-8 border-2 border-emerald-500 border-t-transparent rounded-full mx-auto" />
          <p className="text-slate-400 text-sm font-semibold">{t('common.loading')}</p>
        </div>
      </div>
    )
  }

  if (!appUser) {
    return (
      <div className="min-h-screen bg-brand-primary flex items-center justify-center p-6 font-sans relative overflow-hidden">
        {/* Glow Effects */}
        <div className="absolute -right-32 -top-32 w-96 h-96 rounded-full bg-emerald-500/10 blur-3xl pointer-events-none" />
        <div className="absolute -left-32 -bottom-32 w-96 h-96 rounded-full bg-indigo-500/5 blur-3xl pointer-events-none" />
        
        <div className="w-full max-w-md space-y-6 z-10">
          <div className="text-center">
            <img src={`${import.meta.env.BASE_URL}logo-default.svg`} alt="prismdeals Logo" className="w-64 h-auto mx-auto" />
          </div>


          <Card className="p-6 space-y-4">
            <form onSubmit={handleLoginSubmit} className="space-y-4">
              <div className="space-y-1.5">
                <label className="text-2xs text-slate-500 font-bold uppercase tracking-wider block">
                  {t('auth.emailLabel')}
                </label>
                <Input
                  type="email"
                  value={loginEmail}
                  onChange={e => setLoginEmail(e.target.value)}
                  placeholder={t('auth.emailPlaceholder')}
                  required
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-2xs text-slate-500 font-bold uppercase tracking-wider block">
                  {t('auth.passwordLabel')}
                </label>
                <Input
                  type="password"
                  value={loginPassword}
                  onChange={e => setLoginPassword(e.target.value)}
                  placeholder={t('auth.passwordPlaceholder')}
                  required
                />
              </div>

              {loginError && (
                <div className="bg-rose-500/10 border border-rose-500/25 p-3 rounded-xl text-xs text-rose-400 font-bold animate-fadeIn">
                  {loginError}
                </div>
              )}

              <Button
                type="submit"
                variant="primary"
                disabled={isLoggingIn}
                className="w-full py-3"
              >
                {isLoggingIn ? t('auth.buttonLoggingIn') : t('auth.buttonLogin')}
              </Button>
            </form>
          </Card>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-brand-primary text-slate-100 flex flex-col font-sans">
      {/* Header */}
      <header className="h-16 border-b border-border-subtle bg-bg-surface/60 backdrop-blur-md sticky top-0 z-40 px-6 flex items-center justify-between">
        <div className="flex items-center space-x-3 cursor-pointer" onClick={() => navigate('landing', null, null)}>
          <img src={`${import.meta.env.BASE_URL}logo-icon.svg`} alt="prismdeals Icon" className="w-8 h-8 rounded-lg shadow shadow-black/30" />
          <span className="font-semibold text-lg tracking-wide text-white font-sans">prismdeals</span>
        </div>

        {/* Hamburger Menu Toggle for Mobile */}
        <button
          onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
          className="md:hidden p-2 text-text-muted hover:text-white transition-colors focus:outline-none"
          aria-label="Toggle menu"
        >
          {isMobileMenuOpen ? <X className="w-6 h-6 animate-fade-in" /> : <Menu className="w-6 h-6 animate-fade-in" />}
        </button>

        {/* Desktop Controls (Inline row) */}
        <div className="hidden md:flex items-center gap-4">
          {/* Authentication session state widget */}
          <div className="flex items-center gap-3 bg-bg-input border border-border-subtle rounded-xl py-1.5 px-3 shadow-inner">
            <div className="flex items-center space-x-1.5">
              <span className={cn("w-2 h-2 rounded-full", sessionEmail ? 'bg-emerald-500 animate-pulse' : 'bg-rose-500')} />
              <span className="text-2xs font-semibold text-text-muted">
                {sessionEmail ? t('common.sessionActive', { email: sessionEmail }) : t('common.sessionUnauth')}
              </span>
            </div>

            {!sessionEmail ? (
              <Button
                variant="mini-emerald"
                size="xs"
                onClick={handleTriggerLogin}
                disabled={isScraping || isProcessing}
                className="flex items-center justify-center gap-1"
              >
                <Key className="w-3 h-3" />
                <span>{t('common.login')}</span>
              </Button>
            ) : (
              <Button
                variant="secondary"
                size="xs"
                onClick={handleTriggerLogin}
                disabled={isScraping || isProcessing}
                className="flex items-center justify-center gap-1 border-border-subtle"
              >
                <Key className="w-3 h-3 text-brand-accent" />
                <span>{t('common.reauth')}</span>
              </Button>
            )}
          </div>

          <div className="flex items-center gap-3">
            {/* Language Selector Dropdown */}
            <div className="relative">
              <Button
                variant="badge"
                size="sm"
                onClick={() => setIsLangDropdownOpen(!isLangDropdownOpen)}
                className="px-3 py-1.5 text-2xs flex items-center justify-center gap-1.5 border-border-subtle"
              >
                <Globe className="w-3.5 h-3.5 text-text-muted" />
                <span>{lang.toUpperCase()}</span>
                <ChevronDown className="w-3 h-3 text-text-muted" />
              </Button>

              {isLangDropdownOpen && (
                <>
                  <div className="fixed inset-0 z-10" onClick={() => setIsLangDropdownOpen(false)} />
                  <div className="absolute right-0 mt-1.5 w-24 bg-bg-surface border border-border-subtle rounded-xl shadow-xl z-20 py-1 overflow-hidden animate-fade-in">
                    <button
                      onClick={() => { toggleLanguage(); setIsLangDropdownOpen(false); }}
                      className="w-full text-left px-3 py-1.5 text-xs text-text-secondary hover:bg-bg-surface-hover font-semibold transition-colors"
                    >
                      {lang === 'en' ? 'DEUTSCH' : 'ENGLISH'}
                    </button>
                  </div>
                </>
              )}
            </div>

            <Button
              variant="icon"
              size="sm"
              onClick={() => {
                if (view !== 'settings') {
                  setView('settings');
                }
              }}
              title={t('common.globalSettings')}
              className="p-2 border-border-subtle hover:border-brand-accent/30"
            >
              <Settings className="w-4.5 h-4.5 text-text-muted hover:text-brand-accent transition-all duration-300" />
            </Button>
            <Button
              variant="badge"
              size="sm"
              onClick={handleLogout}
              className="px-3 py-1.5 text-2xs text-rose-400 border-rose-500/20 hover:bg-rose-500/10 flex items-center justify-center gap-1.5 text-center"
            >
              <LogOut className="w-3.5 h-3.5" />
              <span>{t('auth.logout')}</span>
            </Button>
          </div>
        </div>
      </header>



      {/* Mobile Navigation Drawer Sheet (slide-out overlay) */}
      {isMobileMenuOpen && (
        <>
          <div 
            className="fixed inset-0 bg-black/60 backdrop-blur-sm z-40 md:hidden animate-fade-in" 
            onClick={() => setIsMobileMenuOpen(false)} 
          />
          <div className="fixed top-0 right-0 bottom-0 w-72 bg-bg-surface border-l border-border-subtle p-6 z-50 flex flex-col gap-6 md:hidden animate-slide-left shadow-2xl">
            <div className="flex items-center justify-between border-b border-border-subtle pb-4">
              <span className="font-bold text-sm text-white tracking-wide uppercase">Navigation</span>
              <button 
                onClick={() => setIsMobileMenuOpen(false)}
                className="p-1 rounded-lg border border-border-subtle text-text-muted hover:text-white"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Authentication session state widget */}
            <div className="flex flex-col gap-3 bg-bg-input border border-border-subtle rounded-xl p-3 shadow-inner">
              <div className="flex items-center space-x-1.5">
                <span className={cn("w-2 h-2 rounded-full", sessionEmail ? 'bg-emerald-500 animate-pulse' : 'bg-rose-500')} />
                <span className="text-2xs font-semibold text-text-muted">
                  {sessionEmail ? t('common.sessionActive', { email: sessionEmail }) : t('common.sessionUnauth')}
                </span>
              </div>

              {!sessionEmail ? (
                <Button
                  variant="mini-emerald"
                  size="sm"
                  onClick={() => { handleTriggerLogin(); setIsMobileMenuOpen(false); }}
                  disabled={isScraping || isProcessing}
                  className="w-full flex items-center justify-center gap-1.5"
                >
                  <Key className="w-3.5 h-3.5" />
                  <span>{t('common.login')}</span>
                </Button>
              ) : (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => { handleTriggerLogin(); setIsMobileMenuOpen(false); }}
                  disabled={isScraping || isProcessing}
                  className="w-full flex items-center justify-center gap-1.5 border-border-subtle"
                >
                  <Key className="w-3.5 h-3.5 text-brand-accent" />
                  <span>{t('common.reauth')}</span>
                </Button>
              )}
            </div>

            {/* Language toggle button for Mobile */}
            <div className="space-y-1">
              <span className="text-2xs font-bold text-text-muted uppercase tracking-wider block font-mono">Language</span>
              <Button
                variant="badge"
                size="sm"
                onClick={toggleLanguage}
                className="w-full justify-between px-3 border-border-subtle"
              >
                <span className="flex items-center gap-2">
                  <Globe className="w-4.5 h-4.5 text-text-muted" />
                  <span>{lang === 'en' ? 'ENGLISH' : 'DEUTSCH'}</span>
                </span>
                <span className="text-2xs text-brand-accent font-bold">Switch to {lang === 'en' ? 'DE' : 'EN'}</span>
              </Button>
            </div>

            {/* Actions list */}
            <div className="space-y-3 mt-auto">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => {
                  setView('settings');
                  setIsMobileMenuOpen(false);
                }}
                className="w-full justify-start gap-2.5"
              >
                <Settings className="w-4.5 h-4.5 text-text-muted" />
                <span>{t('common.globalSettings')}</span>
              </Button>

              <Button
                variant="badge"
                size="sm"
                onClick={() => { handleLogout(); setIsMobileMenuOpen(false); }}
                className="w-full justify-start gap-2.5 text-rose-400 border-rose-500/20 hover:bg-rose-500/10"
              >
                <LogOut className="w-4 h-4" />
                <span>{t('auth.logout')}</span>
              </Button>
            </div>
          </div>
        </>
      )}


      {/* Main Container */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-6 flex flex-col justify-start">
        {/* VIEW 1: LANDING VIEW - CAMPAIGN HUB GRID */}
        {view === 'landing' && (
          <div className="space-y-6 animate-fadeIn w-full">
            <div className="flex justify-between items-center pb-4 border-b border-slate-800/80 w-full mb-6">
              <div>
                <h1 className="text-xl font-bold text-slate-200">{t('landing.title')}</h1>
                <p className="text-2xs text-slate-500 font-semibold uppercase tracking-wider">{t('landing.subtitle')}</p>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {campaigns.map(c => {
                const campaignSearches = searches.filter(s => s.campaign_id === c.id)
                const campaignListings = listings.filter(l => {
                  const s = searches.find(x => x.id === l.search_id)
                  return s && s.campaign_id === c.id
                })
                const unprocessedCount = campaignListings.filter(l => !l.llm_processed).length
                const firstListingWithImages = campaignListings.find(l => l.images && l.images.length > 0)
                const firstImg = firstListingWithImages?.images?.[0]

                return (
                  <Card
                    interactive
                    key={c.id}
                    onClick={() => {
                      const campaignSearches = searches.filter(s => s.campaign_id === c.id);
                      if (campaignSearches.length === 0) {
                        navigate('edit', c.id, null);
                      } else {
                        navigate('dashboard', c.id);
                      }
                    }}
                    className="p-4 justify-between space-y-4"
                  >
                    {firstImg ? (
                      <div className="w-full aspect-[21/9] rounded-xl overflow-hidden relative border border-slate-800 shadow-inner">
                        <img
                          src={firstImg}
                          alt={c.name}
                          className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"
                        />
                        <div className="absolute inset-0 bg-gradient-to-t from-slate-950 via-slate-950/20 to-transparent" />
                      </div>
                    ) : (
                      <div className="w-full aspect-[21/9] rounded-xl relative border border-slate-800/80 bg-gradient-to-br from-indigo-500/10 via-slate-950 to-emerald-500/5 flex items-center justify-center overflow-hidden">
                        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-indigo-500/5 via-transparent to-transparent" />
                        <span className="text-2xs font-bold text-slate-600 uppercase tracking-widest font-mono">{t('landing.noListings')}</span>
                      </div>
                    )}

                    <div className="flex-1 flex flex-col justify-between pt-1">
                      <div className="space-y-2">
                        <div className="flex justify-between items-start">
                          <div>
                            <h3 className="text-sm font-extrabold text-slate-200 group-hover:text-emerald-400 transition-colors tracking-tight line-clamp-1">{c.name}</h3>
                            <p className="text-2xs text-slate-500 font-semibold uppercase tracking-wider mt-0.5">{t('landing.profileType')}</p>
                          </div>

                          <div className="flex items-center gap-1 shrink-0">
                            <Button
                              variant="icon"
                              size="xs"
                              onClick={(e) => {
                                e.stopPropagation();
                                const firstTarget = searches.find(s => s.campaign_id === c.id);
                                navigate('edit', c.id, firstTarget?.id || null);
                              }}
                              title={t('landing.configureTooltip')}
                              className="p-1.5"
                            >
                              <Settings className="w-5 h-5 transition-transform duration-500 hover:rotate-90 text-text-muted hover:text-brand-accent" />
                            </Button>
                            <Button
                              variant="icon"
                              size="xs"
                              onClick={(e) => {
                                e.stopPropagation();
                                handleDeleteCampaign(c.id, c.name, campaignSearches.length, campaignListings.length);
                              }}
                              title={t('landing.deleteTooltip')}
                              className="p-1.5"
                            >
                              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
                                   strokeLinecap="round" strokeLinejoin="round"
                                   className="w-5 h-5 text-text-muted hover:text-rose-400 transition-colors"
                                   aria-hidden="true">
                                <path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
                              </svg>
                            </Button>
                          </div>
                        </div>

                        <div className="flex flex-wrap gap-1.5 text-2xs font-semibold">
                          <span className="bg-slate-950/60 text-slate-400 border border-slate-855 px-2 py-0.5 rounded-md">
                            {campaignSearches.length} {t('landing.targets')}
                          </span>
                          <span className="bg-slate-950/60 text-emerald-400 border border-emerald-500/10 px-2 py-0.5 rounded-md font-bold">
                            {campaignListings.length} {t('landing.matches')}
                          </span>
                          {unprocessedCount > 0 && (
                            <span className="bg-indigo-500/15 text-indigo-400 border border-indigo-500/25 px-2 py-0.5 rounded-md font-extrabold animate-pulse">
                              {unprocessedCount} {t('landing.new')}
                            </span>
                          )}
                        </div>
                      </div>

                      <div className="border-t border-slate-855 mt-4 pt-3 flex justify-between items-center text-xs text-slate-400 font-bold">
                        <span className="group-hover:text-emerald-400 transition-colors flex items-center space-x-1">
                          <span>{t('landing.openDashboard')}</span>
                          <span className="transform group-hover:translate-x-1 transition-transform">&rarr;</span>
                        </span>
                      </div>
                    </div>
                  </Card>
                )
              })}

              {/* "+" Add Hunt Campaign Card */}
              <Card
                interactive
                onClick={() => setView('create-campaign')}
                className="bg-slate-900/20 border-dashed border-slate-800 hover:border-emerald-500/50 hover:bg-emerald-500/[0.02] p-6 items-center justify-center space-y-4 h-full min-h-[220px]"
              >
                <div className="w-12 h-12 rounded-2xl bg-emerald-500/10 text-emerald-400 flex items-center justify-center font-bold text-xl group-hover:bg-emerald-500 group-hover:text-slate-950 transition-all shadow-inner">
                  +
                </div>
                <div className="text-center">
                  <h3 className="text-sm font-bold text-slate-300 group-hover:text-emerald-400 transition-colors">{t('landing.createCampaign')}</h3>
                  <p className="text-2xs text-slate-500 mt-1 max-w-[200px]">{t('landing.createSubtitle')}</p>
                </div>
              </Card>
            </div>
          </div>
        )}

        {/* VIEW 2: CAMPAIGN DASHBOARD - FEED LISTINGS VIEW */}
        {view === 'dashboard' && (
          <div className="flex flex-col space-y-6 animate-fadeIn w-full">

            {/* Campaign Breadcrumb Headers & Filters */}
            <Card className="flex flex-col md:flex-row md:items-center justify-between gap-4 p-4 md:p-5">
              <div className="flex flex-wrap items-center gap-3 w-full md:w-auto">
                <Button
                  variant="badge"
                  size="sm"
                  onClick={() => {
                    navigate('landing', null, null);
                  }}
                  className="px-3 py-1.5"
                >
                  <span className="mr-1">←</span>
                  <span>{t('common.backToCampaigns')}</span>
                </Button>
                <span className="text-text-muted hidden sm:inline">|</span>
                <div className="flex items-center space-x-2">
                  <h2 className="text-base font-bold text-white">
                    {campaigns.find(c => c.id === currentCampaignId)?.name} {t('listing.dashboardTitle')}
                  </h2>

                  <Button
                    variant="icon"
                    size="xs"
                    onClick={() => {
                      const firstTarget = searches.find(s => s.campaign_id === currentCampaignId);
                      navigate('edit', currentCampaignId, firstTarget?.id || null);
                    }}
                    title={t('landing.configureTooltip')}
                    className="p-1.5 border-border-subtle hover:border-brand-accent/30"
                  >
                    <Settings className="w-4 h-4 transition-transform duration-500 hover:rotate-90 text-text-muted hover:text-brand-accent" />
                  </Button>
                </div>
              </div>

              <div className="flex flex-col lg:flex-row lg:items-center gap-4 w-full md:w-auto">
                {/* Crawler and AI control actions */}
                <div className="grid grid-cols-3 gap-2 w-full lg:w-auto">
                  <Button
                    variant="action-emerald"
                    size="sm"
                    onClick={handleStartScrape}
                    disabled={isScraping || isProcessing}
                    className="py-2.5 px-2 text-center flex items-center justify-center gap-1.5"
                  >
                    <Search className="w-3.5 h-3.5" />
                    <span>{t('dashboard.fetchFresh')}</span>
                  </Button>
                  <Button
                    variant="action-sky"
                    size="sm"
                    onClick={handleStartDeepUpdate}
                    disabled={isScraping || isProcessing}
                    className="py-2.5 px-2 text-center flex items-center justify-center gap-1.5"
                  >
                    <RefreshCw className="w-3.5 h-3.5" />
                    <span>{t('dashboard.updateDesc')}</span>
                  </Button>
                  <Button
                    variant="action-indigo"
                    size="sm"
                    onClick={handleStartProcess}
                    disabled={isScraping || isProcessing}
                    className="py-2.5 px-2 text-center flex items-center justify-center gap-1.5"
                  >
                    <Sparkles className="w-3.5 h-3.5" />
                    <span>{t('dashboard.autoAi')}</span>
                  </Button>
                </div>

                {/* Filter dropdowns */}
                <div className="flex flex-col sm:flex-row gap-2 w-full lg:w-auto">
                  {/* Target search filter */}
                  <Select
                    value={selectedSearchId}
                    onChange={setSelectedSearchId}
                    options={[
                      { value: 'All', label: t('dashboard.filterAllSearches') },
                      ...searches
                        .filter(s => s.campaign_id === currentCampaignId)
                        .map(s => ({ value: String(s.id), label: s.name }))
                    ]}
                    className="w-full sm:w-44"
                  />

                  <Select
                    value={selectedStatusFilter}
                    onChange={val => setSelectedStatusFilter(val as 'All' | 'High Niceness' | 'New' | 'Evaluate with AI')}
                    options={[
                      { value: 'All', label: t('dashboard.statusAll') },
                      { value: 'High Niceness', label: `${t('dashboard.statusMatches')} (70+)` },
                      { value: 'Evaluate with AI', label: t('dashboard.statusPending') },
                      { value: 'New', label: t('dashboard.statusEvaluated') }
                    ]}
                    className="w-full sm:w-44"
                  />
                </div>

              </div>
            </Card>

            <ScraperProgressCard
              isScraping={isScraping}
              scrapingStatus={scrapingStatus}
              scrapingProgress={scrapingProgress}
              liveLogs={liveLogs}
              showLogConsole={showLogConsole}
              setShowLogConsole={setShowLogConsole}
            />

            {isProcessing && (
              <div className="bg-indigo-500/5 border border-indigo-500/20 p-4 rounded-2xl flex items-center space-x-3 text-xs text-indigo-400">
                <div className="animate-pulse w-3 h-3 rounded-full bg-indigo-400" />
                <span className="font-semibold">{processingStatus}</span>
              </div>
            )}

            {/* Grid/Split of Matched Listings */}
            {filteredListings.length === 0 ? (
              <div className="bg-slate-900/20 border border-dashed border-border-subtle rounded-2xl p-16 text-center shadow-inner">
                <span className="text-sm text-slate-500 font-semibold block mb-1">No matching listings found</span>
                <span className="text-xs text-slate-600 block">Configure search targets, link guidelines checklists, and trigger scraper discovery crawls to harvest deals.</span>
              </div>
            ) : (
              <div className="flex flex-col lg:flex-row gap-6 items-start w-full relative">
                
                {/* Left Master List / Mobile Grid */}
                <div className={cn(
                  "w-full flex-1 flex flex-col gap-4",
                  "lg:w-[380px] lg:max-w-[380px] lg:flex-initial lg:max-h-[calc(100vh-220px)] lg:overflow-y-auto lg:pr-2 scrollbar-thin"
                )}>
                  {/* Grid on mobile, vertical list on desktop */}
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-1 gap-4">
                    {filteredListings.map(l => (
                      <ListingDetailCard
                        key={l.id}
                        l={l}
                        activeProcessingListingIds={activeProcessingListingIds}
                        handleProcessSingleListing={handleProcessSingleListing}
                        selectedListingId={selectedListingId}
                        setSelectedListingId={setSelectedListingId}
                        mode="list"
                      />
                    ))}
                  </div>
                </div>

                {/* Right Detail Inspector (Desktop) */}
                <div className="hidden lg:block lg:flex-1 lg:sticky lg:top-24 bg-bg-surface border border-border-subtle rounded-2xl p-6 shadow-xl max-h-[calc(100vh-220px)] overflow-y-auto scrollbar-thin w-full">
                  {selectedListingId ? (
                    (() => {
                      const selectedListing = listings.find(l => l.id === selectedListingId);
                      return selectedListing ? (
                        <ListingDetailCard
                          l={selectedListing}
                          activeProcessingListingIds={activeProcessingListingIds}
                          handleProcessSingleListing={handleProcessSingleListing}
                          selectedListingId={selectedListingId}
                          setSelectedListingId={setSelectedListingId}
                          mode="detail"
                        />
                      ) : (
                        <div className="h-full flex flex-col items-center justify-center text-center p-8 text-text-muted">
                          <p className="text-xs font-semibold">Listing not found</p>
                        </div>
                      );
                    })()
                  ) : (
                    <div className="h-[350px] flex flex-col items-center justify-center text-center p-8 text-text-muted border border-dashed border-border-subtle rounded-xl bg-bg-input/20">
                      <Sparkles className="w-8 h-8 text-brand-accent/40 mb-3 animate-pulse" />
                      <p className="text-xs font-semibold">{t('listing.selectListingPrompt') || 'Select a listing from the list to view its full AI evaluation, specs, and outreach drafts.'}</p>
                    </div>
                  )}
                </div>

                {/* Mobile Drawer Overlay / Dialog Modal for Details (lg:hidden) */}
                {selectedListingId && (
                  <div className="fixed inset-0 z-50 flex items-center justify-center p-4 lg:hidden animate-fade-in">
                    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm" onClick={() => setSelectedListingId(null)} />
                    <div className="bg-bg-surface border border-border-subtle w-full max-w-lg max-h-[85vh] rounded-2xl overflow-y-auto p-5 relative z-10 shadow-2xl animate-slide-up">
                      <button
                        onClick={() => setSelectedListingId(null)}
                        className="absolute right-4 top-4 text-text-muted hover:text-white p-1 rounded-lg border border-border-subtle bg-bg-input"
                      >
                        <X className="w-4 h-4" />
                      </button>
                      {(() => {
                        const selectedListing = listings.find(l => l.id === selectedListingId);
                        return selectedListing ? (
                          <div className="mt-4">
                            <ListingDetailCard
                              l={selectedListing}
                              activeProcessingListingIds={activeProcessingListingIds}
                              handleProcessSingleListing={handleProcessSingleListing}
                              selectedListingId={selectedListingId}
                              setSelectedListingId={setSelectedListingId}
                              mode="detail"
                            />
                          </div>
                        ) : null;
                      })()}
                    </div>
                  </div>
                )}

              </div>
            )}
          </div>
        )}
            {/* VIEW 3: CAMPAIGN TARGETS & GUIDELINES EDITOR */}
        {view === 'edit' && (
          <div className="flex flex-col space-y-6 w-full animate-fadeIn max-w-6xl mx-auto py-2">

            {/* Sub Header */}
            <div className="flex justify-between items-center pb-4 border-b border-slate-800 w-full">
              <div className="flex items-center space-x-3">
                <Button
                  variant="badge"
                  size="sm"
                  onClick={() => setView('dashboard')}
                >
                  <span>← {t('common.backToDashboard')}</span>
                </Button>
                <div className="w-[1px] h-5 bg-slate-800" />
                <div className="flex flex-col">
                  {isEditingCampaignName ? (
                    <div className="flex items-center space-x-2">
                      <Input
                        type="text"
                        value={campaigns.find(c => c.id === currentCampaignId)?.name || ''}
                        onChange={e => handleUpdateCampaignName(e.target.value)}
                        onBlur={() => setIsEditingCampaignName(false)}
                        onKeyDown={e => {
                          if (e.key === 'Enter') {
                            setIsEditingCampaignName(false);
                          }
                        }}
                        className="py-1 text-sm rounded-lg"
                        autoFocus
                      />
                      <Button
                        variant="primary"
                        size="xs"
                        onClick={() => setIsEditingCampaignName(false)}
                      >
                        {t('common.done')}
                      </Button>
                    </div>
                  ) : (
                    <div className="flex items-center space-x-2 group">
                      <h1 className="text-base font-bold text-slate-200">
                        {campaigns.find(c => c.id === currentCampaignId)?.name} {t('common.settings')}
                      </h1>
                      <Button
                        variant="icon"
                        size="xs"
                        onClick={() => setIsEditingCampaignName(true)}
                        title={t('common.renameCampaign')}
                        className="p-1"
                      >
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                          <path d="M18.5 2.5a2.121 2.121 0 1 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                        </svg>
                      </Button>
                    </div>
                  )}
                  <p className="text-2xs text-slate-500 font-semibold uppercase tracking-wider mt-0.5">{t('common.targetsAndGuidelines')}</p>
                </div>
              </div>
            </div>

            {activeSearches.length === 0 ? (
              // The card widens for the route corridor: two place fields, two
              // sliders and a suggestion list do not fit in the column that
              // suits a single URL. `overflow-hidden` would clip the
              // suggestions, so it only applies when there is nothing to clip.
              <Card className={`p-8 mx-auto w-full relative animate-fadeIn ${
                routeMode ? 'max-w-3xl' : 'max-w-xl overflow-hidden'
              }`}>
                <div className="absolute -right-16 -top-16 w-36 h-36 rounded-full bg-emerald-500/5 blur-3xl pointer-events-none" />
                
                <div className="space-y-1.5 text-center">
                  <span className="mx-auto text-2xs bg-emerald-500/10 text-emerald-400 font-bold px-2.5 py-0.5 rounded uppercase tracking-wider w-fit block">{t('common.campaignTargetConfig')}</span>
                  <h2 className="text-lg font-bold text-slate-200 font-sans tracking-tight">{t('common.pasteSearchUrl')}</h2>
                  <p className="text-xs text-slate-400 leading-relaxed font-semibold">{t('wizard.targetsDescription')}</p>
                </div>

                <div className="space-y-4 pt-2">
                  <div className="space-y-1.5">
                    <label className="text-2xs text-slate-500 font-bold uppercase tracking-wider block">{t('common.pasteSearchUrl')}</label>
                    <Input
                      type="text"
                      value={newTargetUrl}
                      onChange={e => setNewTargetUrl(e.target.value)}
                      placeholder={t('common.searchUrlPlaceholder')}
                      className="font-mono"
                    />
                  </div>

                  {/* Where to search: around the URL's own place, or along a drive. */}
                  <div className="flex rounded-xl bg-slate-950/60 border border-slate-855 p-1 text-xs font-bold">
                    {[
                      { key: false, label: t('common.searchModePoint') },
                      { key: true, label: t('common.searchModeRoute') },
                    ].map(mode => (
                      <button
                        key={String(mode.key)}
                        type="button"
                        onClick={() => { setRouteMode(mode.key); setRouteError(null); }}
                        aria-pressed={routeMode === mode.key}
                        className={`flex-1 rounded-lg px-3 py-2 transition-colors ${
                          routeMode === mode.key
                            ? 'bg-emerald-500/15 text-emerald-300'
                            : 'text-slate-400 hover:text-slate-200'
                        }`}
                      >
                        {mode.label}
                      </button>
                    ))}
                  </div>

                  {routeMode && (
                    <div className="bg-slate-950/60 border border-slate-855 rounded-2xl p-4 space-y-4 shadow-inner animate-fadeIn">
                      <p className="text-xs text-slate-400 leading-relaxed">{t('common.routeExplainer')}</p>

                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <PlaceInput
                          label={t('common.routeFrom')}
                          placeholder={t('common.routePlaceholder')}
                          value={routeFrom}
                          onChange={setRouteFrom}
                          emptyHint={t('common.routeNoMatches')}
                        />
                        <PlaceInput
                          label={t('common.routeTo')}
                          placeholder={t('common.routePlaceholder')}
                          value={routeTo}
                          onChange={setRouteTo}
                          emptyHint={t('common.routeNoMatches')}
                        />
                      </div>

                      <div className="grid grid-cols-2 gap-3">
                        <div className="space-y-1.5">
                          <label htmlFor="route-corridor" className="text-2xs text-slate-500 font-bold uppercase tracking-wider block">
                            {t('common.routeCorridor')}: <span className="text-slate-300 font-mono">{routeCorridorKm} km</span>
                          </label>
                          <input
                            id="route-corridor"
                            type="range"
                            min={5}
                            max={routeRadiusKm - 5}
                            step={5}
                            value={routeCorridorKm}
                            onChange={e => setRouteCorridorKm(Number(e.target.value))}
                            className="w-full accent-emerald-500"
                          />
                        </div>
                        <div className="space-y-1.5">
                          <label htmlFor="route-radius" className="text-2xs text-slate-500 font-bold uppercase tracking-wider block">
                            {t('common.routeRadius')}: <span className="text-slate-300 font-mono">{routeRadiusKm} km</span>
                          </label>
                          <input
                            id="route-radius"
                            type="range"
                            min={20}
                            max={60}
                            step={5}
                            value={routeRadiusKm}
                            onChange={e => {
                              const next = Number(e.target.value);
                              setRouteRadiusKm(next);
                              // A corridor at least as wide as the circles cannot
                              // be covered at any spacing, so it cannot be asked for.
                              if (routeCorridorKm > next - 5) setRouteCorridorKm(next - 5);
                            }}
                            className="w-full accent-emerald-500"
                          />
                        </div>
                      </div>

                      {(() => {
                        // What is still missing, in the order the form asks for
                        // it. A disabled control that does not say why is a dead
                        // end; naming the next step turns it into an instruction.
                        const blocker =
                          !newTargetUrl || !isValidKleinanzeigenUrl(newTargetUrl)
                            ? t('common.routeNeedsUrl')
                            : !routeFrom && !routeTo
                              ? t('common.routeNeedsBoth')
                              : !routeFrom
                                ? t('common.routeNeedsFrom')
                                : !routeTo
                                  ? t('common.routeNeedsTo')
                                  : null;

                        return (
                          <div className="space-y-2">
                            <button
                              type="button"
                              onClick={handlePlanCorridor}
                              disabled={routePlanning || blocker !== null}
                              aria-describedby={blocker ? 'route-blocker' : undefined}
                              className="w-full rounded-xl bg-emerald-500/15 text-emerald-300 border border-emerald-500/20 px-4 py-3 text-base font-bold hover:bg-emerald-500/25 disabled:bg-slate-900/60 disabled:text-slate-600 disabled:border-slate-800 disabled:cursor-not-allowed transition-colors"
                            >
                              {routePlanning ? t('common.planningCorridor') : t('common.planCorridor')}
                            </button>
                            {blocker && !routePlanning && (
                              <p id="route-blocker" className="text-2xs text-slate-500 text-center">{blocker}</p>
                            )}
                          </div>
                        );
                      })()}

                      {routeError && (
                        <div className="text-xs bg-rose-500/10 text-rose-400 px-3.5 py-2.5 rounded-xl border border-rose-500/10 font-bold animate-fadeIn">
                          {routeError}
                        </div>
                      )}
                      {routeResult && (
                        <div className="text-xs bg-emerald-500/10 text-emerald-400 px-3.5 py-2.5 rounded-xl border border-emerald-500/10 font-bold animate-fadeIn">
                          {t('common.corridorPlanned', { count: routeResult.count, width: routeResult.width })}
                        </div>
                      )}
                    </div>
                  )}

                  {/* Reactive Indicators Panel */}
                  {!routeMode && newTargetUrl && (
                    <div className="bg-slate-950/60 border border-slate-855 rounded-2xl p-4 space-y-3 shadow-inner animate-fadeIn">
                      <div className="text-xs font-bold text-slate-400 border-b border-slate-900 pb-1.5 flex justify-between items-center">
                        <span>{t('common.diagnostics')}</span>
                        {previewLoading && (
                          <div className="flex items-center space-x-1">
                            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
                            <span className="text-2xs text-emerald-400 font-mono">{t('common.processing')}</span>
                          </div>
                        )}
                      </div>

                      {/* URL Validity indicator */}
                      <div className="flex items-center space-x-2 text-xs">
                        <span className="text-2xs font-mono w-24 text-slate-500">{t('common.urlStatus')}</span>
                        {isValidKleinanzeigenUrl(newTargetUrl) ? (
                          <span className="text-emerald-400 font-semibold">{t('common.validUrl')}</span>
                        ) : (
                          <span className="text-rose-400 font-semibold">{t('common.invalidUrl')}</span>
                        )}
                      </div>

                      {/* Suggested Title */}
                      {isValidKleinanzeigenUrl(newTargetUrl) && (
                        <div className="flex items-center space-x-2 text-xs">
                          <span className="text-2xs font-mono w-24 text-slate-500">{t('common.suggestedName')}</span>
                          <span className="text-slate-200 font-bold bg-slate-900 px-2 py-0.5 rounded border border-slate-800">
                            {suggestTitleFromUrl(newTargetUrl) || t('common.extractingTitle')}
                          </span>
                        </div>
                      )}

                      {/* Diagnostic Logs */}
                      {previewLoading && (
                        <div className="text-xs text-slate-400 space-y-1 font-mono pt-1">
                          <div className="flex items-center space-x-1.5">
                            <span className="text-emerald-400">&gt;</span>
                            <span>{t('common.diagnosticLog1')}</span>
                          </div>
                          <div className="flex items-center space-x-1.5">
                            <span className="text-emerald-400">&gt;</span>
                            <span>{t('common.diagnosticLog2')}</span>
                          </div>
                          <div className="flex items-center space-x-1.5">
                            <span className="text-emerald-400">&gt;</span>
                            <span>{t('common.diagnosticLog3')}</span>
                          </div>
                          <div className="flex items-center space-x-1.5">
                            <span className="text-emerald-400">&gt;</span>
                            <span>{t('common.diagnosticLog4')}</span>
                          </div>
                        </div>
                      )}

                      {previewCount !== null && (
                        <div className="text-xs bg-emerald-500/10 text-emerald-400 px-3.5 py-2.5 rounded-xl border border-emerald-500/10 font-bold animate-fadeIn">
                          {t('common.foundCount', { count: previewCount })}
                        </div>
                      )}

                      {previewError && (
                        <div className="text-xs bg-rose-500/10 text-rose-400 px-3.5 py-2.5 rounded-xl border border-rose-500/10 font-bold animate-fadeIn">
                          {previewError}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </Card>
            ) : (
              /* DIRECT 3-STEP GUIDELINES WIZARD WORKSPACE */
              <div className="w-full animate-fadeIn">
                {activeSearchTarget && (
                  <GuidelinesWizard
                    activeSearchTarget={activeSearchTarget}
                    marketMemo={marketMemo}
                    setMarketMemo={setMarketMemo}
                    sampledListings={sampledListings}
                    sampledListingsLoading={sampledListingsLoading}
                    fetchSampleListings={fetchSampleListings}
                    researcherOutput={researcherOutput}
                    setResearcherOutput={setResearcherOutput}
                    researchPromptTemplate={researchPromptTemplate}
                    marketPromptTemplate={marketPromptTemplate}
                    profilePromptTemplate={profilePromptTemplate}
                    editKsError={editKsError}
                    wizardStep={wizardStep}
                    setWizardStep={setWizardStep}
                    handleSaveKnowledgeSet={handleSaveKnowledgeSet}
                    parsedExpertKnowledge={parsedExpertKnowledge}
                    parsedGoodRef={parsedGoodRef}
                    parsedBadRef={parsedBadRef}
                    parsedDemoMsg={parsedDemoMsg}
                    parsedItemJson={parsedItemJson}
                    isScraping={isScraping}
                    scrapingStatus={scrapingStatus}
                    scrapingProgress={scrapingProgress}
                  />
                )}
              </div>
            )}
          </div>
        )}

        {/* VIEW 4: CREATE NEW CAMPAIGN VIEW */}
        {view === 'create-campaign' && (
          <div className="flex flex-col items-center justify-center space-y-6 w-full animate-fadeIn py-12 max-w-lg mx-auto">
            <Card className="p-8 w-full relative overflow-hidden">
              {/* Abstract decorative glowing orb */}
              <div className="absolute -right-16 -top-16 w-36 h-36 rounded-full bg-emerald-500/10 blur-3xl pointer-events-none" />
              <div className="absolute -left-16 -bottom-16 w-36 h-36 rounded-full bg-indigo-500/5 blur-3xl pointer-events-none" />

              <div className="space-y-2">
                <div className="flex items-center space-x-2">
                  <Button
                    variant="badge"
                    size="xs"
                    onClick={() => setView('landing')}
                  >
                    <span>&larr; {t('common.back')}</span>
                  </Button>
                </div>
                <h2 className="text-xl font-extrabold text-slate-200 font-sans tracking-tight">{t('wizard.createCampaignTitle')}</h2>
                <p className="text-xs text-slate-400 leading-relaxed font-medium">{t('wizard.createCampaignDesc')}</p>
              </div>

              <div className="space-y-4 pt-2">
                <div className="space-y-1.5">
                  <label className="text-2xs text-slate-500 font-bold uppercase tracking-wider block">{t('wizard.campaignNameLabel')}</label>
                  <Input
                    type="text"
                    value={newCampaignName}
                    onChange={e => setNewCampaignName(e.target.value)}
                    placeholder={t('wizard.campaignNamePlaceholder')}
                    onKeyDown={async (e) => {
                      if (e.key === 'Enter' && newCampaignName.trim()) {
                        const newId = await handleCreateCampaign();
                        if (newId) {
                          navigate('edit', newId, null);
                        }
                      }
                    }}
                  />
                </div>
              </div>

              <div className="flex space-x-3 pt-4">
                <Button
                  variant="secondary"
                  onClick={() => setView('landing')}
                  className="flex-1 py-3"
                >
                  {t('common.cancel')}
                </Button>
                <Button
                  variant="primary"
                  onClick={async () => {
                    if (!newCampaignName.trim()) return;
                    const newId = await handleCreateCampaign();
                    if (newId) {
                      navigate('edit', newId, null);
                    }
                  }}
                  className="flex-1 py-3"
                >
                  {t('common.save')} &rarr;
                </Button>
              </div>
            </Card>
          </div>
        )}

        {view === 'settings' && (
          <SettingsView onBack={() => setView(previousView)} />
        )}
      </main>
    </div>
  )
}
