/**
 * Application routes - works for both SSR and client-side rendering.
 */

import React from 'react';
import { Routes, Route, Navigate, useNavigate, useParams, useLocation } from 'react-router';
import { Helmet } from 'react-helmet-async';
import { useAuth } from './context/AuthContext';
import App from './App';
import { Homepage } from './components/Homepage';
import { AuthScreen } from './components/AuthScreen';
import { GalleryPage } from './pages/GalleryPage';
import { GalleryPiecePage } from './pages/GalleryPiecePage';
import { ReplayPage } from './pages/ReplayPage';
import type { SSRData } from './entry-server';

interface AppRoutesProps {
  initialData?: unknown;
}

export function AppRoutes({ initialData }: AppRoutesProps): React.ReactElement {
  const ssrData = initialData as SSRData | undefined;

  return (
    <Routes>
      {/* Public routes */}
      <Route path="/" element={<HomepageRoute />} />
      <Route path="/gallery" element={<GalleryRoute initialData={ssrData} />} />
      <Route
        path="/gallery/:userId/:pieceId"
        element={<GalleryPieceRoute initialData={ssrData} />}
      />

      {/* Auth routes */}
      <Route path="/auth/callback" element={<AuthCallback />} />
      <Route path="/studio" element={<StudioRoute />} />

      {/* Dev-only client-render harness (render-study.py --compare) */}
      {import.meta.env.DEV && <Route path="/replay" element={<ReplayPage />} />}

      {/* Fallback */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

function HomepageRoute(): React.ReactElement {
  const navigate = useNavigate();

  const handleEnter = (): void => {
    navigate('/studio');
  };

  return (
    <>
      <Helmet>
        <title>Code Monet - Autonomous AI Artist</title>
        <meta
          name="description"
          content="Code Monet - An autonomous AI artist, painting in real-time. Watch artificial intelligence create original artwork stroke by stroke."
        />
        <meta property="og:title" content="Code Monet - Autonomous AI Artist" />
        <meta
          property="og:description"
          content="Watch as artificial intelligence creates original artwork, stroke by stroke. Each piece emerges from a continuous stream of creative consciousness."
        />
        <meta property="og:type" content="website" />
        <meta property="og:image" content="https://monet.dmfenton.net/og-image.png" />
        <meta property="og:image:width" content="1200" />
        <meta property="og:image:height" content="630" />
        <meta property="og:image:alt" content="Code Monet - AI-Powered Generative Art" />
        <meta property="og:url" content="https://monet.dmfenton.net/" />
        <meta name="twitter:card" content="summary_large_image" />
        <meta name="twitter:image" content="https://monet.dmfenton.net/og-image.png" />
        <link rel="canonical" href="https://monet.dmfenton.net/" />

        <script type="application/ld+json">
          {JSON.stringify({
            '@context': 'https://schema.org',
            '@graph': [
              {
                '@type': 'SoftwareApplication',
                '@id': 'https://monet.dmfenton.net/#app',
                name: 'Code Monet',
                applicationCategory: 'Art',
                operatingSystem: 'Web',
                description:
                  'An autonomous AI artist that paints original artwork in real-time, stroke by stroke.',
                url: 'https://monet.dmfenton.net/',
                image: 'https://monet.dmfenton.net/og-image.png',
                offers: { '@type': 'Offer', price: '0', priceCurrency: 'USD' },
              },
              {
                '@type': 'WebSite',
                '@id': 'https://monet.dmfenton.net/#site',
                url: 'https://monet.dmfenton.net/',
                name: 'Code Monet',
                publisher: { '@id': 'https://monet.dmfenton.net/#person' },
                inLanguage: 'en-US',
              },
              {
                '@type': 'Person',
                '@id': 'https://monet.dmfenton.net/#person',
                name: 'Daniel Fenton',
                url: 'https://dmfenton.net/',
                sameAs: ['https://github.com/dmfenton'],
              },
            ],
          })}
        </script>
      </Helmet>
      <Homepage onEnter={handleEnter} />
    </>
  );
}

function GalleryRoute({ initialData }: { initialData?: SSRData }): React.ReactElement {
  return (
    <>
      <Helmet>
        <title>Gallery - Code Monet</title>
        <meta
          name="description"
          content="Browse the gallery of original artwork created by Code Monet, an autonomous AI artist. Each piece is uniquely conceived and executed in real-time."
        />
        <meta property="og:title" content="Gallery - Code Monet" />
        <meta
          property="og:description"
          content="Original artwork created by an autonomous AI artist. Browse the ever-growing collection of AI-generated paintings."
        />
        <meta property="og:type" content="website" />
        <meta property="og:image" content="https://monet.dmfenton.net/og-image.png" />
        <meta property="og:image:width" content="1200" />
        <meta property="og:image:height" content="630" />
        <meta property="og:image:alt" content="Code Monet - AI-Powered Generative Art" />
        <meta property="og:url" content="https://monet.dmfenton.net/gallery" />
        <meta name="twitter:card" content="summary_large_image" />
        <meta name="twitter:image" content="https://monet.dmfenton.net/og-image.png" />
        <link rel="canonical" href="https://monet.dmfenton.net/gallery" />

        <script type="application/ld+json">
          {JSON.stringify({
            '@context': 'https://schema.org',
            '@type': 'CollectionPage',
            '@id': 'https://monet.dmfenton.net/gallery#page',
            url: 'https://monet.dmfenton.net/gallery',
            name: 'Gallery - Code Monet',
            description: 'Browse the gallery of original AI-generated artwork by Code Monet.',
            isPartOf: { '@id': 'https://monet.dmfenton.net/#site' },
            mainEntity: {
              '@type': 'ItemList',
              numberOfItems: initialData?.galleryPieces?.length ?? 0,
              itemListElement: (initialData?.galleryPieces ?? []).slice(0, 20).map((p, idx) => ({
                '@type': 'ListItem',
                position: idx + 1,
                url: `https://monet.dmfenton.net/gallery/${p.user_id}/${p.id}`,
              })),
            },
          })}
        </script>
      </Helmet>
      <GalleryPage initialGalleryPieces={initialData?.galleryPieces} />
    </>
  );
}

function GalleryPieceRoute({ initialData }: { initialData?: SSRData }): React.ReactElement {
  const { userId, pieceId } = useParams<{ userId: string; pieceId: string }>();
  const piece = initialData?.galleryPiece;
  const strokes = initialData?.pieceStrokes;

  const pieceNumber = piece?.piece_number ?? parseInt(pieceId?.replace('piece_', '') ?? '0', 10);
  const title = piece?.title ?? `Piece No. ${String(pieceNumber).padStart(3, '0')}`;
  const description =
    piece?.description ??
    `Original artwork created by Code Monet, an autonomous AI artist. Piece ${pieceNumber} features ${piece?.stroke_count ?? 'multiple'} unique brushstrokes.`;

  // Generate dynamic OG image URL that can be rendered server-side
  const ogImageUrl = `https://monet.dmfenton.net/api/public/gallery/${userId}/${pieceId}/og-image.png`;

  return (
    <>
      <Helmet>
        <title>{title} - Code Monet</title>
        <meta name="description" content={description} />
        <meta property="og:title" content={title} />
        <meta property="og:description" content={description} />
        <meta property="og:type" content="article" />
        <meta property="og:image" content={ogImageUrl} />
        <meta property="og:image:width" content="1200" />
        <meta property="og:image:height" content="630" />
        <meta
          property="og:url"
          content={`https://monet.dmfenton.net/gallery/${userId}/${pieceId}`}
        />
        <meta name="twitter:card" content="summary_large_image" />
        <meta name="twitter:title" content={title} />
        <meta name="twitter:description" content={description} />
        <meta name="twitter:image" content={ogImageUrl} />
        <link rel="canonical" href={`https://monet.dmfenton.net/gallery/${userId}/${pieceId}`} />

        {/* JSON-LD structured data for artwork */}
        <script type="application/ld+json">
          {JSON.stringify({
            '@context': 'https://schema.org',
            '@type': 'VisualArtwork',
            name: title,
            description: description,
            creator: {
              '@type': 'SoftwareApplication',
              name: 'Code Monet',
              description: 'An autonomous AI artist powered by Claude',
              url: 'https://monet.dmfenton.net',
            },
            artform: 'Digital Painting',
            artMedium: 'SVG/Digital',
            image: ogImageUrl,
            url: `https://monet.dmfenton.net/gallery/${userId}/${pieceId}`,
            dateCreated: piece?.created_at,
            artworkSurface: 'Digital Canvas',
          })}
        </script>
      </Helmet>
      <GalleryPiecePage
        userId={userId ?? ''}
        pieceId={pieceId ?? ''}
        initialPiece={piece}
        initialStrokes={strokes}
      />
    </>
  );
}

function AuthCallback(): React.ReactElement {
  const navigate = useNavigate();
  const location = useLocation();
  const { setTokensFromCallback } = useAuth();
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    const hash = location.hash.substring(1);
    const params = new URLSearchParams(hash);
    const accessToken = params.get('access_token');
    const refreshToken = params.get('refresh_token');

    if (accessToken && refreshToken) {
      const result = setTokensFromCallback(accessToken, refreshToken);
      if (result.success) {
        navigate('/studio', { replace: true });
      } else {
        setError(result.error ?? 'Authentication failed');
      }
    } else {
      setError('Invalid callback URL - missing tokens');
    }
  }, [location.hash, navigate, setTokensFromCallback]);

  const handleBack = (): void => {
    navigate('/');
  };

  return (
    <div className="auth-loading">
      {error ? (
        <div className="auth-error">
          <p>{error}</p>
          <button onClick={handleBack}>Back to Home</button>
        </div>
      ) : (
        <div className="auth-spinner" />
      )}
    </div>
  );
}

function StudioRoute(): React.ReactElement {
  const navigate = useNavigate();
  const { isLoading, isAuthenticated } = useAuth();

  const handleBack = (): void => {
    navigate('/');
  };

  if (isLoading) {
    return (
      <div className="auth-loading">
        <div className="auth-spinner" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <AuthScreen onBack={handleBack} />;
  }

  return <App />;
}
