const algosdk = require('algosdk');
const { subtle } = require('crypto').webcrypto;

async function deriveFromBIP39(mnemonic) {
    const words = mnemonic.trim().split(/\s+/);
    console.log(`Word count: ${words.length}`);
    
    // BIP39 seed derivation
    const salt = Buffer.from('mnemonic');
    const mnemonicBuffer = Buffer.from(mnemonic, 'utf8');
    
    // Import key for HMAC-SHA512
    const key = await subtle.importKey(
        'raw', 
        Buffer.from(salt), 
        { name: 'HMAC', hash: 'SHA-512' }, 
        false, 
        ['sign']
    );
    
    const signature = await subtle.sign('HMAC-SHA512', key, mnemonicBuffer);
    const seed = Buffer.from(signature);
    
    console.log(`Seed: ${seed.toString('hex').substring(0, 32)}...`);
    
    // For Algorand we need ed25519 key derivation
    // Using path m/44'/283'/0'/0/0
    const masterKey = seed; // This is simplified
    
    // Use algosdk's mnemonicToSecretKey which works with 25-word only
    // For 24-word, we need special handling
    try {
        const acc = algosdk.mnemonicToSecretKey(mnemonic);
        console.log(`SUCCESS! Address: ${acc.addr.toString()}`);
    } catch(e) {
        console.log(`Standard method failed: ${e.message}`);
        console.log(`Your 24-word mnemonic requires conversion using BIP39->Ed25519 derivation.`);
        console.log(`Try using the Pera Wallet web interface or bip39toalgo tool to get the address.`);
    }
}

deriveFromBIP39('twist style music hollow opinion job clump bind army push credit chaos average drink object season jeans despair target random excess daring ticket renew');