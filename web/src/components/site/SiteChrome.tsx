/**
 * Public-site header and footer (landing, gallery, piece pages).
 */

import React from 'react';
import { Link } from 'react-router';
import { BrandMark, Wordmark } from '../brand/BrandMark';

interface SiteHeaderProps {
  /** In-page anchors (landing) or a breadcrumb trail (gallery pages). */
  children?: React.ReactNode;
}

export function SiteHeader({ children }: SiteHeaderProps): React.ReactElement {
  return (
    <header className="site-header">
      <div className="site-header-inner">
        <Link to="/" className="site-brand" aria-label="Code Monet home">
          <Wordmark size="md" />
        </Link>
        <div className="site-header-right">
          {children}
          <Link to="/studio" className="btn btn-primary site-enter">
            Enter studio
          </Link>
        </div>
      </div>
    </header>
  );
}

export function SiteFooter(): React.ReactElement {
  return (
    <footer className="site-footer">
      <div className="site-footer-inner">
        <p className="site-footer-credit">
          <BrandMark size={16} />
          <span>
            Built with{' '}
            <a href="https://anthropic.com" target="_blank" rel="noopener noreferrer">
              Claude
            </a>{' '}
            by{' '}
            <a href="https://dmfenton.net" target="_blank" rel="noopener noreferrer">
              Daniel Fenton
            </a>
          </span>
        </p>
        <p className="site-footer-links">
          <a href="https://github.com/dmfenton" target="_blank" rel="noopener noreferrer">
            GitHub
          </a>
          <a href="https://linkedin.com/in/dmfenton" target="_blank" rel="noopener noreferrer">
            LinkedIn
          </a>
          <a href="https://dmfenton.net" className="mono-link">
            a dmfenton.net project
          </a>
        </p>
      </div>
    </footer>
  );
}
