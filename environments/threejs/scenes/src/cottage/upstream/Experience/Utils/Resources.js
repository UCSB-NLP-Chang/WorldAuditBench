import { TextureLoader, CubeTextureLoader } from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { DRACOLoader } from 'three/examples/jsm/loaders/DRACOLoader.js'
import { RGBELoader } from 'three/examples/jsm/loaders/RGBELoader.js'
import { EXRLoader } from 'three/examples/jsm/loaders/EXRLoader.js'

import EventEmitter from './EventEmitter.js'
import Experience from '../Experience.js'

// Offline single-file build: every asset path is turned into a blob: URL by the bootstrap.
const resolveAsset = (path) =>
    window.__resolveAsset ? window.__resolveAsset(path) : path

export default class Resources extends EventEmitter {
    constructor(sources) {
        super()

        this.experience = new Experience()

        // Options
        this.sources = sources

        // Setup
        this.items = {}
        this.toLoad = this.sources.length
        this.loaded = 0

        this.setLoaders()
        this.startLoading()
    }

    setLoaders() {
        this.loaders = {}

        this.loaders.dracoLoader = new DRACOLoader()
        // the fetch override in the bootstrap maps these two files to the embedded decoder
        this.loaders.dracoLoader.setDecoderPath('draco/gltf/')
        this.loaders.gltfLoader = new GLTFLoader()
        this.loaders.gltfLoader.setDRACOLoader(this.loaders.dracoLoader)

        this.loaders.textureLoader = new TextureLoader()
        this.loaders.cubeTextureLoader = new CubeTextureLoader()
        this.loaders.rgbeLoader = new RGBELoader()
        this.loaders.exrLoader = new EXRLoader()
    }

    startLoading() {
        // Loop each source
        for (const source of this.sources) {
            const url = resolveAsset(source.path)
            const fail = (error) => {
                console.error(`Resource "${source.path}" failed.`, error)
            }
            if (source.type === 'gltfModel') {
                this.loaders.gltfLoader.load(
                    url,
                    (file) => this.sourceLoaded(source, file),
                    () => {},
                    fail
                )
            } else if (source.type === 'texture') {
                this.loaders.textureLoader.load(
                    url,
                    (file) => this.sourceLoaded(source, file),
                    () => {},
                    fail
                )
            } else if (source.type === 'cubeTexture') {
                this.loaders.cubeTextureLoader.load(
                    source.path.map(resolveAsset),
                    (file) => this.sourceLoaded(source, file)
                )
            } else if (source.type === 'rgbeTexture') {
                this.loaders.rgbeLoader.load(
                    url,
                    (file) => this.sourceLoaded(source, file),
                    () => {},
                    fail
                )
            } else if (source.type === 'exrTexture') {
                this.loaders.exrLoader.load(
                    url,
                    (file) => this.sourceLoaded(source, file),
                    () => {},
                    fail
                )
            } else if (source.type === 'audio') {
                const file = new Audio(url)
                this.sourceLoaded(source, file)
            }
        }
    }

    sourceLoaded(source, file) {
        this.items[source.name] = file

        this.loaded++
        this.trigger('loading')

        if (this.loaded === this.toLoad) {
            this.trigger('ready')
        }
    }
}
