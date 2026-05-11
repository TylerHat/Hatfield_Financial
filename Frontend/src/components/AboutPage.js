import React from 'react';
import './AboutPage.css';

const EXPERIENCE = [
  {
    role: 'Software Engineer',
    company: 'Pluralsight',
    dates: 'Nov 2024 – Present · Remote',
    description:
      'Configure and develop AI agents to strengthen abuse detection across the lab platform. Build Ruby and Python SDKs that minimize cloud costs, monitor lab-instance spend, and research AWS, Azure, and GCP policy updates to flag high-cost services before they ship.',
  },
  {
    role: 'Software Engineer 2',
    company: 'Polaris Automation',
    dates: 'Apr 2023 – Oct 2024 · Remote',
    description:
      'Built Flask API endpoints, designed BigQuery and MySQL schemas with stored procedures, and delivered Ignition front-ends and PowerBI reporting for a multi-million dollar Whirlpool program. Led an internal certification initiative — workshops on AngularJS, Python, and Terraform.',
  },
  {
    role: 'System Engineer',
    company: 'Grantek',
    dates: 'Jul 2021 – Dec 2022 · Cleveland, OH',
    description:
      'Built a real-time facility monitoring system on Ignition and wrote Python (Jython, Matplotlib, NumPy) analytics for downtime and equipment utilization. Authored SQL queries to surface productivity metrics by shift.',
  },
  {
    role: 'System Engineer',
    company: 'RoviSys',
    dates: 'Dec 2018 – Jul 2021 · Cleveland, OH',
    description:
      'Authored UAT documentation for OEM projects, validated MySQL data records for Alcon, and built HMI screens plus Pandas/SciPy reporting logic for CIP sequences. Wrote onboarding documentation that shortened new-engineer ramp-up.',
  },
  {
    role: 'Manufacturing Engineering Intern',
    company: 'Integral Aerospace',
    dates: 'May 2017 – Aug 2018 · Orange County, CA',
    description:
      'Applied lean manufacturing to reduce delinquent orders, built automated reports for complex production data, and led a team that constructed a Delta Electronics PLC for an automated test stand.',
  },
];

export default function AboutPage() {
  return (
    <div className="about-panel">
      <header className="about-header">
        <img
          className="about-photo"
          src="/about/profile-placeholder.svg"
          alt="Tyler Hatfield"
        />
        <div className="about-intro">
          <h2>Tyler Hatfield</h2>
          <p className="about-tagline">
            Software &amp; Cloud Engineer · Builder of Hatfield Financial
          </p>
          <a
            className="about-linkedin"
            href="https://www.linkedin.com/in/tylerdhatfield/"
            target="_blank"
            rel="noopener noreferrer"
          >
            View LinkedIn Profile →
          </a>
        </div>
      </header>

      <section className="about-section">
        <h3>Summary</h3>
        <p>
          Software and cloud engineer with 7+ years of experience building data-driven
          applications across manufacturing automation, industrial monitoring, and
          developer-education platforms. Currently a Software Engineer at Pluralsight,
          focused on AI-driven abuse detection and cloud-cost optimization across AWS,
          Azure, and GCP. Comfortable across the stack — Python, Ruby, Flask, React —
          and at home in cloud infrastructure with Terraform, ECS Fargate, BigQuery,
          and CI/CD pipelines.
        </p>
      </section>

      <section className="about-section">
        <h3>Experience</h3>
        <ul className="about-experience">
          {EXPERIENCE.map((item) => (
            <li key={`${item.company}-${item.dates}`}>
              <div className="about-experience__title">{item.role}</div>
              <div className="about-experience__meta">
                {item.company} · {item.dates}
              </div>
              <p className="about-experience__desc">{item.description}</p>
            </li>
          ))}
        </ul>
      </section>

      <section className="about-section about-section--columns">
        <div>
          <h3>Education</h3>
          <p>
            <strong>Miami University</strong>
            <br />
            B.E., Manufacturing Engineering (2014 – 2018)
          </p>
        </div>
        <div>
          <h3>Certifications</h3>
          <ul className="about-certs">
            <li>Microsoft Certified: Azure Fundamentals (2026)</li>
            <li>AWS Certified Solutions Architect – Associate (2022)</li>
          </ul>
        </div>
      </section>

      <section className="about-section">
        <h3>This Project</h3>
        <p>
          Hatfield Financial is a real-time financial analyst platform with
          trading-strategy signals across the S&amp;P 500 and beyond. React + Flask,
          yfinance / pandas / numpy data pipelines, deployed on AWS (ECS Fargate, ECR,
          S3, CloudFront, Route 53, API Gateway) via Terraform with a GitHub Actions
          CI/CD pipeline.
        </p>
      </section>
    </div>
  );
}
