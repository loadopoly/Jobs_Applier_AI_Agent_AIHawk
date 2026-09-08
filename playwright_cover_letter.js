const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

async function launchBrowser() {
  try {
    return await chromium.launch({ headless: true });
  } catch (err) {
    try {
      return await chromium.launch({ channel: 'msedge', headless: true });
    } catch (edgeErr) {
      return await chromium.launch({ channel: 'chrome', headless: true });
    }
  }
}

function extractSkillsFromMarkup(htmlContent, textContent) {
  // 1. First try the user's original regex
  let requiredMatch = textContent.match(/Required Qualifications:?(.*?)[.!?\n]/is)?.[1];
  let required = requiredMatch
    ? requiredMatch.split(/[,;•]/g).map(s => s.trim()).filter(Boolean)
    : [];

  let preferredMatch = textContent.match(/Preferred Qualifications:?(.*?)[.!?\n]/is)?.[1];
  let preferred = preferredMatch
    ? preferredMatch.split(/[,;•]/g).map(s => s.trim()).filter(Boolean)
    : [];

  // 2. Intelligent fallback if requiredSkills was not matched by specific phrase
  if (required.length === 0) {
    // Look for HTML list items after QUALIFICATIONS / Requirements / Qualifications heading
    const qualRegex = /(?:QUALIFICATIONS|Qualifications|Basic Qualifications|Requirements):?<\/p>\s*<ul>(.*?)<\/ul>/is;
    const qualHtmlMatch = htmlContent.match(qualRegex);

    if (qualHtmlMatch) {
      const liMatches = [...qualHtmlMatch[1].matchAll(/<li>(.*?)<\/li>/gis)].map(m => m[1].replace(/<[^>]+>/g, '').trim());
      // Extract concise skill phrases from the top qualifications
      const extracted = [];
      for (const item of liMatches) {
        if (item.toLowerCase().includes('procurement') || item.toLowerCase().includes('sourcing')) {
          extracted.push('global procurement & strategic sourcing');
        } else if (item.toLowerCase().includes('far') || item.toLowerCase().includes('dfars') || item.toLowerCase().includes('regulation')) {
          extracted.push('FAR/DFARS compliance');
        } else if (item.toLowerCase().includes('supply chain') || item.toLowerCase().includes('logistics')) {
          extracted.push('global supply chain leadership');
        } else if (item.toLowerCase().includes('vendor') || item.toLowerCase().includes('subcontract')) {
          extracted.push('subcontract & vendor management');
        } else if (item.toLowerCase().includes('transform')) {
          extracted.push('supply chain transformation');
        }
      }
      if (extracted.length > 0) {
        required = [...new Set(extracted)];
      } else if (liMatches.length > 0) {
        // Use summarized first bullet point or snippet
        const firstBullet = liMatches[0].split(/[.;]/)[0].trim();
        required = [firstBullet];
      }
    }
  }

  // 3. Fallback to generic supply chain skills if still empty
  if (required.length === 0) {
    required = ['global procurement', 'strategic sourcing', 'supply chain optimization'];
  }

  return { required, preferred };
}

async function generateCoverLetter(targetUrl) {
  const jobUrl = targetUrl || process.argv[2] || 'https://www.linkedin.com/jobs/view/4451271011/';
  console.log(`[JobHawk Playwright] Navigating to: ${jobUrl}`);

  const browser = await launchBrowser();
  const page = await browser.newPage({
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
  });

  try {
    await page.goto(jobUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.waitForTimeout(2000);

    // Extract key details from the job description
    const rawJobTitle = await page.textContent('h1').catch(() => '');
    const jobTitle = (rawJobTitle || 'Professional Role').trim();

    const rawCompanyName = await page.textContent('.topcard__org-name-link').catch(() => '')
      || await page.textContent('.job-card-container__company-name').catch(() => '')
      || await page.textContent('.topcard__flavor--black-link').catch(() => '');
    const companyName = (rawCompanyName || 'Hiring Team').trim();

    const jobDescription = (await page.textContent('.show-more-less-html__markup').catch(() => '')).trim();
    const jobHtml = await page.innerHTML('.show-more-less-html__markup').catch(() => '');

    const { required: requiredSkills, preferred: preferredSkills } = extractSkillsFromMarkup(jobHtml, jobDescription);

    // Create cover letter sections tailored to the job
    const contactBlock = `Adam Gard
Baltimore, MD 21224
(443) 617-4612
adam.gard@alum.mit.edu`;

    const openingParagraph = `Dear Hiring Manager,

I am excited to apply for the ${jobTitle} position at ${companyName}. With my strong background in supply chain engineering, ERP integration, and inventory optimization, I am confident I would be a valuable addition to your team.`;

    const keyQualifications = `As Sr. Principal Supply Chain Engineer at Astec Industries, I have:
- Built AstecHub, a unified supply chain platform integrating rate management, PPV, and inventory control across multiple ERPs
- Achieved 100% policy compliance and ≥95% SKU accuracy by leading cycle count programs across manufacturing facilities
- Developed an AI agent that reduced maintenance downtime by 42%, emergency procurement by 37%, and MTTR by 29%
- Reduced on-hand SKUs by 96.4% while maintaining 98.3% stock-out confidence through ML-driven segmentation
- Realized $1.02M+ in savings via team upskilling and reduced inventory variance from $1.2M to $40K`;

    const closingParagraph = `My military logistics background, combined with my ${requiredSkills.join(', ')} skills, make me uniquely qualified for this role. I would welcome the chance to discuss how I can help ${companyName} achieve its goals.

Thank you for your consideration.

Sincerely,
Adam Gard`;

    // Assemble the complete cover letter
    const coverLetter = `
${contactBlock}

${openingParagraph}

${keyQualifications}

${closingParagraph}
`.trim();

    console.log('\n=================== GENERATED COVER LETTER ===================\n');
    console.log(coverLetter);
    console.log('\n==============================================================\n');

    // Save output to data_folder/output
    const safeCompany = companyName.replace(/[^a-z0-9_-]/gi, '_').toLowerCase();
    const safeTitle = jobTitle.replace(/[^a-z0-9_-]/gi, '_').toLowerCase();
    const outputDir = path.resolve(__dirname, 'data_folder', 'output');
    if (!fs.existsSync(outputDir)) {
      fs.mkdirSync(outputDir, { recursive: true });
    }

    const outputFile = path.join(outputDir, `cover_letter_${safeCompany}_${safeTitle}.txt`);
    fs.writeFileSync(outputFile, coverLetter, 'utf-8');
    console.log(`[JobHawk Playwright] Saved cover letter to: ${outputFile}`);

    return {
      coverLetter,
      jobTitle,
      companyName,
      requiredSkills,
      preferredSkills,
      outputFile,
    };
  } finally {
    await browser.close();
  }
}

if (require.main === module) {
  generateCoverLetter().catch(err => {
    console.error('[JobHawk Playwright] Error generating cover letter:', err);
    process.exit(1);
  });
}

module.exports = { generateCoverLetter, launchBrowser, extractSkillsFromMarkup };
