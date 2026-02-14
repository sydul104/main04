#!/usr/bin/env node

/**
 * M3U8 Link Validator (Node.js)
 * This script tests each m3u8 link from the M3U playlist file and checks their validity.
 */

const fs = require('fs');
const http = require('http');
const https = require('https');
const { URL } = require('url');

// Configuration
const CONFIG = {
    TIMEOUT: 10000, // milliseconds
    MAX_CONCURRENT: 10,
    INPUT_FILE: 'my',
    OUTPUT_FILE: 'm3u8_validation_report.txt',
    USER_AGENT: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
};

class M3U8Validator {
    constructor() {
        this.results = [];
        this.activeRequests = 0;
        this.queue = [];
    }

    /**
     * Extract all m3u8/http links from M3U file
     */
    extractLinksFromM3U(filename) {
        const links = [];
        let currentChannelInfo = '';

        try {
            const content = fs.readFileSync(filename, 'utf-8');
            const lines = content.split('\n');

            for (const line of lines) {
                const trimmedLine = line.trim();

                // Skip empty lines and header
                if (!trimmedLine || trimmedLine === '#EXTM3U') {
                    continue;
                }

                // Extract channel info from metadata
                if (trimmedLine.startsWith('#EXTINF')) {
                    const match = trimmedLine.match(/,(.+)$/);
                    currentChannelInfo = match ? match[1] : 'Unknown Channel';
                }
                // If it's a URL (not commented out)
                else if (trimmedLine.startsWith('http') && !trimmedLine.startsWith('#http')) {
                    links.push({
                        url: trimmedLine,
                        channel: currentChannelInfo,
                        index: links.length + 1
                    });
                    currentChannelInfo = '';
                }
            }

            return links;
        } catch (error) {
            console.error(`Error reading file: ${error.message}`);
            return [];
        }
    }

    /**
     * Test a single m3u8 link
     */
    testLink(linkInfo) {
        return new Promise((resolve) => {
            const { url, channel } = linkInfo;
            const result = {
                url,
                channel,
                status: 'UNKNOWN',
                responseTime: null,
                error: null,
                httpCode: null
            };

            const startTime = Date.now();
            let parsedUrl;

            try {
                parsedUrl = new URL(url);
            } catch (error) {
                result.status = 'INVALID_URL';
                result.error = error.message;
                resolve(result);
                return;
            }

            const protocol = parsedUrl.protocol === 'https:' ? https : http;
            const options = {
                method: 'HEAD',
                timeout: CONFIG.TIMEOUT,
                headers: {
                    'User-Agent': CONFIG.USER_AGENT
                }
            };

            const req = protocol.request(parsedUrl, options, (res) => {
                const responseTime = ((Date.now() - startTime) / 1000).toFixed(2);
                result.httpCode = res.statusCode;
                result.responseTime = responseTime;

                if (res.statusCode === 200) {
                    result.status = 'VALID';
                } else if (res.statusCode === 403) {
                    result.status = 'FORBIDDEN';
                } else if (res.statusCode === 404) {
                    result.status = 'NOT_FOUND';
                } else if (res.statusCode >= 300 && res.statusCode < 400) {
                    result.status = 'REDIRECT';
                } else {
                    result.status = `HTTP_${res.statusCode}`;
                }

                resolve(result);
            });

            req.on('timeout', () => {
                req.destroy();
                result.status = 'TIMEOUT';
                result.error = `Request timed out after ${CONFIG.TIMEOUT / 1000}s`;
                resolve(result);
            });

            req.on('error', (error) => {
                result.status = 'CONNECTION_ERROR';
                result.error = error.message;
                resolve(result);
            });

            req.end();
        });
    }

    /**
     * Process queue with concurrency limit
     */
    async processQueue(links) {
        return new Promise((resolve) => {
            let completed = 0;
            const total = links.length;
            const results = [];

            const processNext = () => {
                while (this.activeRequests < CONFIG.MAX_CONCURRENT && this.queue.length > 0) {
                    const linkInfo = this.queue.shift();
                    this.activeRequests++;

                    this.testLink(linkInfo).then((result) => {
                        results.push(result);
                        completed++;
                        this.activeRequests--;

                        // Print progress
                        const statusSymbol = result.status === 'VALID' ? '✓' : '✗';
                        const channelName = result.channel.substring(0, 40).padEnd(40);
                        console.log(`[${completed}/${total}] ${statusSymbol} ${channelName} - ${result.status}`);

                        if (completed === total) {
                            resolve(results);
                        } else {
                            processNext();
                        }
                    });
                }
            };

            this.queue = [...links];
            processNext();
        });
    }

    /**
     * Validate all links
     */
    async validateAllLinks(links) {
        console.log('\n' + '='.repeat(80));
        console.log(`Testing ${links.length} m3u8 links...`);
        console.log('='.repeat(80) + '\n');

        const results = await this.processQueue(links);
        return results;
    }

    /**
     * Generate validation report
     */
    generateReport(results, outputFile) {
        const validCount = results.filter(r => r.status === 'VALID').length;
        const invalidCount = results.length - validCount;
        const successRate = ((validCount / results.length) * 100).toFixed(2);

        let report = '';
        report += 'M3U8 LINK VALIDATION REPORT\n';
        report += '='.repeat(80) + '\n';
        report += `Generated: ${new Date().toLocaleString()}\n`;
        report += `Total Links Tested: ${results.length}\n`;
        report += `Valid Links: ${validCount}\n`;
        report += `Invalid Links: ${invalidCount}\n`;
        report += `Success Rate: ${successRate}%\n`;
        report += '='.repeat(80) + '\n\n';

        // Valid links section
        report += 'VALID LINKS:\n';
        report += '-'.repeat(80) + '\n';
        results.forEach(r => {
            if (r.status === 'VALID') {
                report += `\n✓ ${r.channel}\n`;
                report += `  URL: ${r.url}\n`;
                report += `  Response Time: ${r.responseTime}s\n`;
            }
        });

        // Invalid links section
        report += '\n\n' + '='.repeat(80) + '\n';
        report += 'INVALID/FAILED LINKS:\n';
        report += '-'.repeat(80) + '\n';
        results.forEach(r => {
            if (r.status !== 'VALID') {
                report += `\n✗ ${r.channel}\n`;
                report += `  URL: ${r.url}\n`;
                report += `  Status: ${r.status}\n`;
                if (r.httpCode) {
                    report += `  HTTP Code: ${r.httpCode}\n`;
                }
                if (r.error) {
                    report += `  Error: ${r.error}\n`;
                }
            }
        });

        // Summary by status
        report += '\n\n' + '='.repeat(80) + '\n';
        report += 'SUMMARY BY STATUS:\n';
        report += '-'.repeat(80) + '\n';

        const statusCounts = {};
        results.forEach(r => {
            statusCounts[r.status] = (statusCounts[r.status] || 0) + 1;
        });

        Object.entries(statusCounts)
            .sort((a, b) => b[1] - a[1])
            .forEach(([status, count]) => {
                report += `${status}: ${count}\n`;
            });

        // Write report to file
        fs.writeFileSync(outputFile, report, 'utf-8');

        console.log('\n' + '='.repeat(80));
        console.log(`Report saved to: ${outputFile}`);
        console.log('='.repeat(80));

        return { validCount, invalidCount, successRate };
    }
}

async function main() {
    console.log('\n' + '='.repeat(80));
    console.log('M3U8 LINK VALIDATOR (Node.js)');
    console.log('='.repeat(80));

    const validator = new M3U8Validator();

    // Extract links from M3U file
    console.log(`\nReading links from '${CONFIG.INPUT_FILE}'...`);
    const links = validator.extractLinksFromM3U(CONFIG.INPUT_FILE);

    if (links.length === 0) {
        console.log('No links found in the file!');
        return;
    }

    console.log(`Found ${links.length} links to test`);

    // Validate all links
    const results = await validator.validateAllLinks(links);

    // Generate report
    const { validCount, invalidCount, successRate } = validator.generateReport(
        results,
        CONFIG.OUTPUT_FILE
    );

    // Print summary
    console.log('\nSUMMARY:');
    console.log(`  Total Links: ${results.length}`);
    console.log(`  Valid: ${validCount} (${successRate}%)`);
    console.log(`  Invalid: ${invalidCount} (${(100 - successRate).toFixed(1)}%)`);
    console.log(`\nDetailed report saved to '${CONFIG.OUTPUT_FILE}'`);
}

// Run the script
main().catch(console.error);
